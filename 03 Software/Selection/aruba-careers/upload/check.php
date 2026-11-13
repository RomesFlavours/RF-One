<?php
/*
 * RF-One · careers page on Aruba — check of the hosting plan
 * (SELECTION_ARUBA_IDENTITY_001).
 *
 * Shows, on the real Aruba plan, whether everything the careers page needs
 * is available: PHP version and extensions, secure random numbers, a
 * writable private folder, sessions, HTTPS, the private folder being closed
 * to the web, and a real authenticated login to the SMTP server (no email
 * is sent unless `&send=1`, and then only to the company mailbox itself).
 * On Aruba Hosting Windows it also proves that web.config keeps private/
 * closed and that the data folder (mdb-database) is writable and closed.
 *
 * Disabled unless `diagnostics_key` is set in private/config.php; open it as
 * check.php?key=<that value>, then empty the key again.
 */

declare(strict_types=1);

define('RFC_APP', true);
require __DIR__ . '/private/lib.php';

header('Cache-Control: no-store');
header('X-Robots-Tag: noindex, nofollow');
header('Content-Type: text/html; charset=utf-8');

try {
    $config = rfc_config();
    $configError = null;
} catch (RfcConfigError $e) {
    $config = is_file(__DIR__ . '/private/config.php') ? (require __DIR__ . '/private/config.php') : [];
    $configError = $e->getMessage();
}
$key = is_array($config) ? (string)($config['diagnostics_key'] ?? '') : '';
if (strlen($key) < 16 || !hash_equals($key, (string)($_GET['key'] ?? ''))) {
    http_response_code(404);
    exit;
}

$rows = [];
$add = function (string $label, bool $ok, string $detail = '') use (&$rows) {
    $rows[] = [$label, $ok, $detail];
};

/** Status line of a GET to a URL of this same site, as the web sees it. */
$fetch = function (string $path): string {
    $url = (rfc_is_https() ? 'https://' : 'http://') . ($_SERVER['HTTP_HOST'] ?? '') . $path;
    $context = stream_context_create(['http' => ['method' => 'GET', 'timeout' => 10, 'ignore_errors' => true],
                                      'ssl' => ['verify_peer' => true, 'verify_peer_name' => true]]);
    $body = @file_get_contents($url, false, $context);
    $status = isset($http_response_header[0]) ? (string)$http_response_header[0] : 'no answer';
    return $status . ($body !== false && strpos($body, 'RF-ONE-PRIVATE-FOLDER-EXPOSED') !== false ? ' EXPOSED' : '');
};
$closed = function (string $status): bool {
    return preg_match('# (403|404) #', $status . ' ') === 1 && strpos($status, 'EXPOSED') === false;
};

$add('Web server', true, (string)($_SERVER['SERVER_SOFTWARE'] ?? 'unknown') . ' · ' . PHP_OS_FAMILY);
$add('PHP version (7.4 or later)', PHP_VERSION_ID >= 70400, PHP_VERSION . ' (' . PHP_SAPI . ')');
foreach (['openssl', 'json', 'session', 'hash', 'pcre', 'filter'] as $ext) {
    $add("PHP extension $ext", extension_loaded($ext));
}
$add('TLS 1.3 constant available', defined('STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT'),
    defined('OPENSSL_VERSION_TEXT') ? OPENSSL_VERSION_TEXT : '');
try {
    $sample = rfc_new_code();
    $add('Secure random code (random_int)', strlen($sample) === RFC_CODE_LENGTH, 'example length ' . strlen($sample));
} catch (Throwable $e) {
    $add('Secure random code (random_int)', false, get_class($e));
}
$add('Configuration private/config.php', $configError === null, $configError ?? 'complete');
$add('HTTPS on this request', rfc_is_https());
$add('Function stream_socket_client allowed', function_exists('stream_socket_client')
    && stripos((string)ini_get('disable_functions'), 'stream_socket_client') === false);
$add('open_basedir', true, (string)ini_get('open_basedir') !== '' ? (string)ini_get('open_basedir') : 'not set');

$status = $fetch(rfc_base_path() . 'private/blocked.html');
$add('Folder private/ closed to the web (web.config)', $closed($status), $status);

if ($configError === null) {
    try {
        $dir = rfc_data_dir('limits');
        $probe = $dir . '/probe-' . bin2hex(random_bytes(4));
        $written = @file_put_contents($probe, 'x') === 1;
        @unlink($probe);
        $add('Data folder writable (sessions, counters, logs)', $written, rfc_data_base());
        rfc_counter('check', 'probe', 60, true);
        $add('Counters with file locking', true);
        // The data folder must not be downloadable: if it lies under the web root, try one file from outside.
        $root = rtrim(str_replace('\\', '/', (string)realpath((string)($_SERVER['DOCUMENT_ROOT'] ?? ''))), '/');
        $base = str_replace('\\', '/', (string)realpath(rfc_data_base()));
        if ($root !== '' && stripos($base . '/', $root . '/') === 0) {
            $name = 'probe-' . bin2hex(random_bytes(6)) . '.html';
            @file_put_contents(rfc_data_base() . '/' . $name, 'RF-ONE-PRIVATE-FOLDER-EXPOSED');
            $status = $fetch(substr($base, strlen($root)) . '/' . $name);
            @unlink(rfc_data_base() . '/' . $name);
            $add('Data folder closed to the web', $closed($status), $status);
        } else {
            $add('Data folder closed to the web', true, 'outside the web root');
        }
    } catch (Throwable $e) {
        $add('Data folder writable (sessions, counters, logs)', false, $e->getMessage());
    }
    try {
        rfc_start_session();
        $_SESSION['check'] = 1;
        $add('PHP sessions in the data folder', session_status() === PHP_SESSION_ACTIVE, session_save_path());
    } catch (Throwable $e) {
        $add('PHP sessions in the data folder', false, $e->getMessage());
    }
    try {
        $send = ($_GET['send'] ?? '') === '1';
        if ($send) {
            rfc_smtp_send($config['smtp'], (string)$config['smtp']['from_address'], 'RF-One careers page: test message',
                "Test message from check.php on the Aruba hosting. No action needed.\n");
        } else {
            rfc_smtp_send($config['smtp']);
        }
        $add('SMTP login ' . $config['smtp']['host'] . ':' . $config['smtp']['port'] . ' (' . $config['smtp']['encryption'] . ')',
            true, $send ? 'test message sent to ' . $config['smtp']['from_address'] : 'login accepted, nothing sent');
    } catch (Throwable $e) {
        $add('SMTP login ' . $config['smtp']['host'] . ':' . $config['smtp']['port'], false, $e->getMessage());
    }
}

$all = array_reduce($rows, function ($carry, $row) { return $carry && $row[1]; }, true);
echo '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    . '<title>Hosting check · Careers</title><link rel="stylesheet" href="assets/careers.css?v=1"></head>'
    . '<body class="public"><div class="wrap"><div class="card"><h1>Hosting check</h1>'
    . '<p class="' . ($all ? 'ok' : 'bad') . '">' . ($all ? 'Everything the careers page needs is available.' : 'Something is missing: see the red lines.') . '</p>'
    . '<table class="check">';
foreach ($rows as $row) {
    echo '<tr><td>' . rfc_h($row[0]) . '</td><td class="' . ($row[1] ? 'ok' : 'bad') . '">' . ($row[1] ? 'OK' : 'NO') . '</td><td>'
        . rfc_h($row[2]) . '</td></tr>';
}
echo '</table><p class="muted">When finished, empty <code>diagnostics_key</code> in private/config.php.</p></div></div></body></html>';
