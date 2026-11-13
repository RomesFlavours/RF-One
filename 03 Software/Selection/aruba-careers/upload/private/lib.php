<?php
/*
 * RF-One Selection — careers page on Aruba (SELECTION_ARUBA_IDENTITY_001).
 *
 * Everything the page needs, in plain PHP 7.4+ with no framework and no
 * library: the 5-digit code (CSPRNG, stored only as an HMAC, 10 minutes,
 * 5 attempts), limits on repeated requests (per email, per network, per
 * failed attempt), authenticated SMTP to the company mailbox, and the signed
 * single-use token handed to Selection on AWS.
 *
 * Hosting: Aruba Hosting Windows (IIS, PHP 8.2). Never served directly:
 * `web.config` hides the `private` folder and this file stops unless included
 * by a page. Everything written at run time (sessions, counters, logs) goes
 * to Aruba's `mdb-database` folder, which is writable and which Aruba never
 * serves to the web (see `rfc_data_dir`).
 *
 * The token must stay identical to the Selection side
 * (`rfone_data_store/selection/identity_handoff_service.py`):
 *   RF1.<base64url(JSON claims)>.<base64url(HMAC-SHA256(secret, "RF1." + claims part))>
 */

declare(strict_types=1);

if (!defined('RFC_APP')) {
    http_response_code(404);
    exit;
}

const RFC_TOKEN_PREFIX = 'RF1';
const RFC_ISSUER = 'rfone-careers-aruba';
const RFC_AUDIENCE = 'rfone-selection';
const RFC_AUTH_METHOD = 'email-code';
const RFC_TOKEN_TTL = 300;              // the token only has to survive the automatic redirect
const RFC_CODE_LENGTH = 5;
const RFC_CODE_TTL = 600;               // 10 minutes
const RFC_MAX_ATTEMPTS = 5;             // per code
const RFC_RESEND_COOLDOWN = 60;         // seconds between two codes for one email
const RFC_CODES_PER_EMAIL_PER_HOUR = 5;
const RFC_CODES_PER_IP_PER_HOUR = 20;
const RFC_FAILED_PER_IP_PER_HOUR = 30;
const RFC_MIN_SECRET_LENGTH = 32;
const RFC_MAX_NAME_LENGTH = 120;
const RFC_POSITION_PATTERN = '/^[A-Za-z0-9_-]{8,64}$/';

final class RfcConfigError extends RuntimeException {}
final class RfcSendError extends RuntimeException {}

/** The configuration in private/config.php, validated once. */
function rfc_config(): array
{
    static $config = null;
    if ($config !== null) {
        return $config;
    }
    $file = __DIR__ . '/config.php';
    if (!is_file($file)) {
        throw new RfcConfigError('private/config.php is missing');
    }
    $loaded = require $file;
    if (!is_array($loaded)) {
        throw new RfcConfigError('private/config.php must return an array');
    }
    $smtp = isset($loaded['smtp']) && is_array($loaded['smtp']) ? $loaded['smtp'] : [];
    foreach (['host', 'port', 'encryption', 'username', 'password', 'from_address'] as $key) {
        if (!isset($smtp[$key]) || $smtp[$key] === '') {
            throw new RfcConfigError("smtp.$key is not set");
        }
    }
    if (!in_array($smtp['encryption'], ['ssl', 'starttls', 'none'], true)) {
        throw new RfcConfigError('smtp.encryption must be ssl, starttls or none');
    }
    $secret = (string)($loaded['handoff_secret'] ?? '');
    if (strlen($secret) < RFC_MIN_SECRET_LENGTH || strpos($secret, 'CHANGE-ME') !== false) {
        throw new RfcConfigError('handoff_secret is not set (at least 32 characters)');
    }
    $target = (string)($loaded['selection_handoff_url'] ?? '');
    $requireHttps = ($loaded['require_https'] ?? true) !== false;
    if (!preg_match($requireHttps ? '#^https://[^/\s]+/\S*$#' : '#^https?://[^/\s]+/\S*$#', $target)) {
        throw new RfcConfigError('selection_handoff_url must be the https address of Selection');
    }
    $loaded['smtp'] = $smtp + ['from_name' => '', 'cafile' => null, 'timeout' => 20];
    $loaded['require_https'] = $requireHttps;
    $loaded['company_name'] = (string)($loaded['company_name'] ?? "Rome's Flavours");
    $config = $loaded;
    return $config;
}

function rfc_h(?string $value): string
{
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function rfc_is_https(): bool
{
    if (!empty($_SERVER['HTTPS']) && strtolower((string)$_SERVER['HTTPS']) !== 'off') {
        return true;
    }
    if (strtolower((string)($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '')) === 'https') {
        return true;
    }
    return (string)($_SERVER['SERVER_PORT'] ?? '') === '443';
}

/** The careers folder as seen from the browser ("/" or "/careers/"), from SCRIPT_NAME (always set by IIS). */
function rfc_base_path(): string
{
    return rtrim(str_replace('\\', '/', dirname((string)($_SERVER['SCRIPT_NAME'] ?? '/'))), '/') . '/';
}

function rfc_client_ip(): string
{
    return substr((string)($_SERVER['REMOTE_ADDR'] ?? 'unknown'), 0, 64);
}

/**
 * The folder for sessions, counters and logs. Unless `data_dir` is set, it is
 * `rfone-careers` inside the first of Aruba's protected data folders
 * (`mdb-database`, then `App_Data`) found next to the careers folder or above
 * it: on Aruba Hosting Windows they are the folders with write permission
 * whose files cannot be downloaded from the web.
 */
function rfc_data_base(): string
{
    static $base = null;
    if ($base !== null) {
        return $base;
    }
    $config = rfc_config();
    if (!empty($config['data_dir'])) {
        return $base = rtrim((string)$config['data_dir'], '/\\');
    }
    $level = dirname(__DIR__);  // the careers folder
    for ($i = 0; $i < 4; $i++) {
        foreach (['mdb-database', 'App_Data'] as $name) {
            if (@is_dir($level . '/' . $name)) {
                return $base = $level . '/' . $name . '/rfone-careers';
            }
        }
        $parent = dirname($level);
        if ($parent === $level) {
            break;
        }
        $level = $parent;
    }
    throw new RfcConfigError("no protected data folder (mdb-database) found: set data_dir");
}

function rfc_data_dir(string $sub = ''): string
{
    $base = rfc_data_base();
    $dir = $sub === '' ? $base : $base . '/' . $sub;
    if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) {
        throw new RfcConfigError('the data folder cannot be created');
    }
    return $dir;
}

/** A short, non-reversible label for logs (an email or network is never written in clear). */
function rfc_pseudonym(string $value): string
{
    return substr(hash_hmac('sha256', 'log|' . strtolower($value), rfc_config()['handoff_secret']), 0, 12);
}

function rfc_log(string $event, array $context = []): void
{
    $line = gmdate('Y-m-d\TH:i:s\Z') . ' ' . $event;
    foreach ($context as $key => $value) {
        $line .= ' ' . $key . '=' . preg_replace('/[^A-Za-z0-9_.:-]/', '_', (string)$value);
    }
    try {
        @file_put_contents(rfc_data_dir('logs') . '/careers-' . gmdate('Y-m') . '.log', $line . "\n", FILE_APPEND | LOCK_EX);
    } catch (Throwable $e) {
        // A log that cannot be written never blocks the candidate.
    }
}

// ---------------------------------------------------------------------------
// Session and form protection
// ---------------------------------------------------------------------------

function rfc_start_session(): void
{
    $config = rfc_config();
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    ini_set('session.use_trans_sid', '0');
    ini_set('session.gc_maxlifetime', '3600');
    try {
        session_save_path(rfc_data_dir('sessions'));
    } catch (Throwable $e) {
        // Fall back to the hosting's default session folder.
    }
    session_cache_limiter('');  // the page sends its own Cache-Control: no-store
    session_name('rfcareers');
    session_set_cookie_params([
        'lifetime' => 0, 'path' => rfc_base_path(), 'secure' => $config['require_https'] || rfc_is_https(),
        'httponly' => true, 'samesite' => 'Lax',
    ]);
    session_start();
}

function rfc_csrf_token(): string
{
    if (empty($_SESSION['csrf'])) {
        $_SESSION['csrf'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf'];
}

function rfc_csrf_ok(): bool
{
    $sent = (string)($_POST['csrf'] ?? '');
    return $sent !== '' && isset($_SESSION['csrf']) && hash_equals($_SESSION['csrf'], $sent);
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

function rfc_clean_name(string $value): string
{
    $value = preg_replace('/[\x00-\x1F\x7F]+/u', ' ', $value);
    $value = trim((string)preg_replace('/\s+/u', ' ', (string)$value));
    if ($value === '' || !preg_match('//u', $value)) {
        return '';
    }
    preg_match('/^.{0,' . RFC_MAX_NAME_LENGTH . '}/us', $value, $m);
    return $m[0];
}

function rfc_clean_email(string $value): string
{
    $value = strtolower(trim($value));
    if (strlen($value) > 254 || preg_match('/[\r\n]/', $value) || !filter_var($value, FILTER_VALIDATE_EMAIL)) {
        return '';
    }
    return $value;
}

function rfc_valid_position(string $value): bool
{
    return (bool)preg_match(RFC_POSITION_PATTERN, $value);
}

// ---------------------------------------------------------------------------
// Code and limits
// ---------------------------------------------------------------------------

/** A new 5-digit code from PHP's cryptographically secure generator. */
function rfc_new_code(): string
{
    return str_pad((string)random_int(0, 99999), RFC_CODE_LENGTH, '0', STR_PAD_LEFT);
}

/** Only this HMAC is kept (in the server-side session); the code itself is never stored or logged. */
function rfc_hash_code(string $code, string $email): string
{
    return hash_hmac('sha256', 'code-v1|' . $email . '|' . $code, rfc_config()['handoff_secret']);
}

/**
 * Timestamps of one counter (a file per email or network, named by an HMAC),
 * read and optionally extended under an exclusive lock.
 */
function rfc_counter(string $kind, string $key, int $window, bool $add): array
{
    $file = rfc_data_dir('limits') . '/' . $kind . '-' . hash_hmac('sha256', $kind . '|' . strtolower($key), rfc_config()['handoff_secret']) . '.json';
    $handle = fopen($file, 'c+');
    if ($handle === false) {
        throw new RfcConfigError('the limits folder is not writable');
    }
    try {
        flock($handle, LOCK_EX);
        $raw = stream_get_contents($handle);
        $stamps = is_string($raw) && $raw !== '' ? json_decode($raw, true) : [];
        $now = time();
        $stamps = array_values(array_filter(is_array($stamps) ? $stamps : [], function ($t) use ($now, $window) {
            return is_int($t) && $t > $now - $window;
        }));
        if ($add) {
            $stamps[] = $now;
            ftruncate($handle, 0);
            rewind($handle);
            fwrite($handle, json_encode($stamps));
            fflush($handle);
        }
        flock($handle, LOCK_UN);
    } finally {
        fclose($handle);
    }
    return $stamps;
}

/** Null when a code may be sent now, otherwise the message to show. */
function rfc_send_refusal(string $email, string $ip): ?string
{
    $forEmail = rfc_counter('code-email', $email, 3600, false);
    if ($forEmail && max($forEmail) > time() - RFC_RESEND_COOLDOWN) {
        $wait = max($forEmail) + RFC_RESEND_COOLDOWN - time();
        return "A code was just sent. Please wait $wait seconds before asking for a new one.";
    }
    if (count($forEmail) >= RFC_CODES_PER_EMAIL_PER_HOUR) {
        return 'Too many codes were requested for this email. Please try again in an hour.';
    }
    if (count(rfc_counter('code-ip', $ip, 3600, false)) >= RFC_CODES_PER_IP_PER_HOUR) {
        return 'Too many codes were requested from this network. Please try again later.';
    }
    return null;
}

function rfc_record_send(string $email, string $ip): void
{
    rfc_counter('code-email', $email, 3600, true);
    rfc_counter('code-ip', $ip, 3600, true);
}

function rfc_too_many_failures(string $ip): bool
{
    return count(rfc_counter('fail-ip', $ip, 3600, false)) >= RFC_FAILED_PER_IP_PER_HOUR;
}

function rfc_record_failure(string $ip): void
{
    rfc_counter('fail-ip', $ip, 3600, true);
}

// ---------------------------------------------------------------------------
// Signed token for Selection
// ---------------------------------------------------------------------------

function rfc_b64url(string $data): string
{
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
}

function rfc_issue_token(string $first, string $last, string $email, string $position): string
{
    $now = time();
    $claims = [
        'v' => 1, 'iss' => RFC_ISSUER, 'aud' => RFC_AUDIENCE, 'amr' => RFC_AUTH_METHOD,
        'jti' => bin2hex(random_bytes(16)), 'iat' => $now, 'exp' => $now + RFC_TOKEN_TTL,
        'pos' => $position, 'fn' => $first, 'ln' => $last, 'em' => $email,
    ];
    $body = rfc_b64url(json_encode($claims, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
    $signed = RFC_TOKEN_PREFIX . '.' . $body;
    return $signed . '.' . rfc_b64url(hash_hmac('sha256', $signed, rfc_config()['handoff_secret'], true));
}

// ---------------------------------------------------------------------------
// Authenticated SMTP (company mailbox on Aruba), one recipient per message
// ---------------------------------------------------------------------------

/** @return resource */
function rfc_smtp_connect(array $smtp)
{
    $tls = ['verify_peer' => true, 'verify_peer_name' => true, 'peer_name' => $smtp['host'],
            'allow_self_signed' => false, 'SNI_enabled' => true,
            'crypto_method' => STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT | STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT];
    if (!empty($smtp['cafile'])) {
        $tls['cafile'] = $smtp['cafile'];
    }
    $context = stream_context_create(['ssl' => $tls]);
    $scheme = $smtp['encryption'] === 'ssl' ? 'ssl://' : 'tcp://';
    $errno = 0;
    $errstr = '';
    $socket = @stream_socket_client($scheme . $smtp['host'] . ':' . (int)$smtp['port'], $errno, $errstr,
        (float)$smtp['timeout'], STREAM_CLIENT_CONNECT, $context);
    if ($socket === false) {
        throw new RfcSendError('connection to the mail server failed (' . $errno . ' ' . $errstr . ')');
    }
    stream_set_timeout($socket, (int)$smtp['timeout']);
    return $socket;
}

/** @param resource $socket */
function rfc_smtp_expect($socket, array $codes, string $step): string
{
    $reply = '';
    while (($line = fgets($socket, 1024)) !== false) {
        $reply .= $line;
        if (strlen($line) < 4 || $line[3] !== '-') {
            break;
        }
    }
    $code = (int)substr($reply, 0, 3);
    if (!in_array($code, $codes, true)) {
        // The server's reply never contains the password or the code; keep it short.
        throw new RfcSendError("mail server refused $step (" . trim(substr($reply, 0, 120)) . ')');
    }
    return $reply;
}

/** @param resource $socket */
function rfc_smtp_command($socket, string $command, array $codes, string $step): string
{
    fwrite($socket, $command . "\r\n");
    return rfc_smtp_expect($socket, $codes, $step);
}

/**
 * Opens an authenticated SMTP session. With $to it sends one message;
 * without, it only proves that connection and login work (diagnostics).
 */
function rfc_smtp_send(array $smtp, ?string $to = null, string $subject = '', string $body = ''): void
{
    $from = (string)$smtp['from_address'];
    $helo = substr(strrchr($from, '@') ?: '@localhost', 1);
    $socket = rfc_smtp_connect($smtp);
    try {
        rfc_smtp_expect($socket, [220], 'greeting');
        rfc_smtp_command($socket, 'EHLO ' . $helo, [250], 'EHLO');
        if ($smtp['encryption'] === 'starttls') {
            rfc_smtp_command($socket, 'STARTTLS', [220], 'STARTTLS');
            if (!stream_socket_enable_crypto($socket, true,
                STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT | STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT)) {
                throw new RfcSendError('TLS could not be started');
            }
            rfc_smtp_command($socket, 'EHLO ' . $helo, [250], 'EHLO');
        }
        rfc_smtp_command($socket, 'AUTH LOGIN', [334], 'AUTH');
        rfc_smtp_command($socket, base64_encode((string)$smtp['username']), [334], 'AUTH user');
        rfc_smtp_command($socket, base64_encode((string)$smtp['password']), [235], 'AUTH password');
        if ($to !== null) {
            rfc_smtp_command($socket, 'MAIL FROM:<' . $from . '>', [250], 'MAIL FROM');
            rfc_smtp_command($socket, 'RCPT TO:<' . $to . '>', [250, 251], 'RCPT TO');
            rfc_smtp_command($socket, 'DATA', [354], 'DATA');
            $name = (string)$smtp['from_name'];
            $headers = [
                'Date: ' . date(DATE_RFC2822),
                'From: ' . ($name !== '' ? '"' . addcslashes($name, '"\\') . '" ' : '') . '<' . $from . '>',
                'To: <' . $to . '>',
                'Subject: ' . $subject,
                'Message-ID: <' . bin2hex(random_bytes(12)) . '@' . $helo . '>',
                'MIME-Version: 1.0',
                'Content-Type: text/plain; charset=UTF-8',
                'Content-Transfer-Encoding: quoted-printable',
                'Auto-Submitted: auto-generated',
            ];
            $message = implode("\r\n", $headers) . "\r\n\r\n"
                . quoted_printable_encode(str_replace(["\r\n", "\r"], "\n", $body));
            $message = preg_replace('/^\./m', '..', str_replace("\n", "\r\n", str_replace("\r\n", "\n", $message)));
            fwrite($socket, $message . "\r\n.\r\n");
            rfc_smtp_expect($socket, [250], 'message');
        }
        fwrite($socket, "QUIT\r\n");
    } finally {
        fclose($socket);
    }
}

function rfc_send_code_email(string $to, string $first, string $code): void
{
    $config = rfc_config();
    $company = $config['company_name'];
    rfc_smtp_send($config['smtp'], $to, "Your $company verification code",
        "Hi $first,\n\nYour verification code is: $code\n\n"
        . "It expires in 10 minutes. If you did not request it, you can ignore this email.\n\n$company\n");
}
