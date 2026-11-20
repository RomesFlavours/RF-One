<?php
declare(strict_types=1);
// Internal functions; direct requests do not expose configuration.
if (!defined('RFONE_ENTRY')) { http_response_code(404); exit; }
$config = require __DIR__ . '/config.php';
function relay(array $fields): array {
    $fields['state'] = $_SESSION['bridge_state'];
    $fields['ip'] = $_SERVER['REMOTE_ADDR'] ?? '';
    return machine_api('/candidate/bridge/relay', $fields);
}
function machine_api(string $path, array $fields): array {
    global $config;
    if (!in_array($path, ['/candidate/bridge/relay', '/candidate/bridge/mail/claim', '/candidate/bridge/mail/ack'], true)) {
        throw new RuntimeException('Invalid Selection endpoint.');
    }
    $body = json_encode((object)$fields, JSON_THROW_ON_ERROR);
    $stamp = (string)time();
    $curl = curl_init($config['aws_base'] . $path);
    curl_setopt_array($curl, [CURLOPT_POST => true, CURLOPT_POSTFIELDS => $body,
        CURLOPT_RETURNTRANSFER => true, CURLOPT_CONNECTTIMEOUT => 10, CURLOPT_TIMEOUT => 30,
        CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_CAINFO => __DIR__ . '/cacert.pem', CURLOPT_IPRESOLVE => CURL_IPRESOLVE_V4,
        CURLOPT_FOLLOWLOCATION => false, CURLOPT_HTTPHEADER => ['Content-Type: application/json',
        'X-RFOne-Time: ' . $stamp, 'X-RFOne-Signature: ' . hash_hmac('sha256', $stamp . "\n" . $body, $config['relay_key'])]]);
    $result = curl_exec($curl);
    $status = (int)curl_getinfo($curl, CURLINFO_HTTP_CODE);
    $connectionError = curl_errno($curl);
    curl_close($curl);
    if ($result === false) { throw new RuntimeException('Unable to connect to Selection (connection ' . $connectionError . '). Please try again.'); }
    $data = json_decode($result, true);
    if (!is_array($data) || !array_key_exists('ok', $data)) {
        if ($status === 400) { throw new RuntimeException('Your session expired. Please close this page and open www.rmaed.it again.'); }
        throw new RuntimeException('Selection connection returned HTTP ' . $status . '. Please try again.');
    }
    return $data;
}
class MailTransportException extends RuntimeException {
    public function __construct(string $message, public bool $uncertain = false, public bool $permanent = false) {
        parent::__construct($message);
    }
}
function smtp_expect($socket, array $expected): void {
    $line = '';
    do {
        $part = fgets($socket, 2048);
        if ($part === false) { throw new MailTransportException('Email server response interrupted.', true); }
        $line = $part;
    } while (isset($part[3]) && $part[3] === '-');
    if (!in_array((int)substr($line, 0, 3), $expected, true)) {
        $code = (int)substr($line, 0, 3);
        throw new MailTransportException('Email server returned SMTP ' . $code . '.', false, $code >= 500);
    }
}
function smtp_command($socket, string $command, array $expected): void {
    $remaining = $command . "\r\n";
    while ($remaining !== '') {
        $sent = fwrite($socket, $remaining);
        if (!$sent) { throw new MailTransportException('Email connection interrupted.', true); }
        $remaining = substr($remaining, $sent);
    }
    smtp_expect($socket, $expected);
}
function deliver_code(string $email, string $code): void {
    if (!preg_match('/^\d{6}$/D', $code)) {
        throw new RuntimeException('Please enter a valid email address.');
    }
    send_selection_email($email, 'Your RF-One Selection verification code',
        "Your verification code is: " . $code . "\n\nIt expires in 10 minutes.\n" .
        "If you did not request this code, you can ignore this email.\n\nRF-One Selection",
        bin2hex(random_bytes(20)) . '@rmaed.it');
}
function encoded_subject(string $subject): string {
    $words = []; $chunk = '';
    foreach (preg_split('//u', $subject, -1, PREG_SPLIT_NO_EMPTY) as $character) {
        if (strlen($chunk . $character) > 42) { $words[] = '=?UTF-8?B?' . base64_encode($chunk) . '?='; $chunk = ''; }
        $chunk .= $character;
    }
    if ($chunk !== '') { $words[] = '=?UTF-8?B?' . base64_encode($chunk) . '?='; }
    return implode("\r\n ", $words);
}
function send_selection_email(string $email, string $subject, string $body, string $messageId): void {
    global $config;
    if (!filter_var($email, FILTER_VALIDATE_EMAIL) || preg_match('/[\r\n]/', $email . $subject) ||
        !preg_match('/^[a-f0-9]{40}@rmaed\.it$/D', $messageId) || strlen($body) > 64000) {
        throw new MailTransportException('Invalid email destination or content.', false, true);
    }
    $context = stream_context_create(['ssl' => ['verify_peer' => true, 'verify_peer_name' => true,
        'peer_name' => 'smtps.aruba.it', 'cafile' => __DIR__ . '/cacert.pem',
        'crypto_method' => STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT | STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT]]);
    $socket = @stream_socket_client('ssl://smtps.aruba.it:465', $errno, $error, 20, STREAM_CLIENT_CONNECT, $context);
    if (!$socket) { throw new MailTransportException('The email server is unavailable. Please try again.'); }
    stream_set_timeout($socket, 20);
    $dataSubmitted = false;
    try {
        smtp_expect($socket, [220]);
        smtp_command($socket, 'EHLO www.rmaed.it', [250]);
        smtp_command($socket, 'AUTH LOGIN', [334]);
        smtp_command($socket, base64_encode($config['smtp_user']), [334]);
        smtp_command($socket, base64_encode($config['smtp_password']), [235]);
        smtp_command($socket, 'MAIL FROM:<' . $config['smtp_user'] . '>', [250]);
        smtp_command($socket, 'RCPT TO:<' . $email . '>', [250, 251]);
        smtp_command($socket, 'DATA', [354]);
        $message = 'From: RF-One Selection <' . $config['smtp_user'] . ">\r\n" .
            'To: <' . $email . ">\r\nSubject: " . encoded_subject($subject) . "\r\n" .
            'Date: ' . date(DATE_RFC2822) . "\r\n" .
            'Message-ID: <' . $messageId . ">\r\n" .
            "MIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n";
        $body = str_replace(["\r\n", "\r"], "\n", $body);
        $body = quoted_printable_encode(str_replace("\n", "\r\n", $body));
        $body = preg_replace('/^\./m', '..', $body);
        $message .= $body . "\r\n.";
        $dataSubmitted = true;
        smtp_command($socket, $message, [250]);
        // The server accepted the message. A failed QUIT must not invalidate its code.
        @fwrite($socket, "QUIT\r\n");
    } catch (MailTransportException $ex) {
        throw new MailTransportException($ex->getMessage(), $dataSubmitted && $ex->uncertain, $ex->permanent);
    } finally { fclose($socket); }
}
function finish_on_aws(string $url): never {
    global $config;
    $expected = $config['aws_base'] . '/candidate/bridge/finish?ticket=';
    if (!str_starts_with($url, $expected) || !preg_match('/^[A-Za-z0-9_-]{43}$/D', substr($url, strlen($expected)))) {
        throw new RuntimeException('Unable to open your application. Please try again.');
    }
    $_SESSION = [];
    session_destroy();
    header('Location: ' . $url, true, 303);
    exit;
}
