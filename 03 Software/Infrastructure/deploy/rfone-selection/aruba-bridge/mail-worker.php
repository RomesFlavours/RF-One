<?php
declare(strict_types=1);
define('RFONE_ENTRY', true);
header('Content-Type: application/json');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
require __DIR__ . '/relay.php';
$body = file_get_contents('php://input');
$stamp = $_SERVER['HTTP_X_RFONE_TIME'] ?? '';
$signature = $_SERVER['HTTP_X_RFONE_SIGNATURE'] ?? '';
$expected = hash_hmac('sha256', $stamp . "\n" . $body, $config['relay_key']);
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !ctype_digit($stamp) || abs(time() - (int)$stamp) > 60 ||
    strlen($body) > 16000 || !hash_equals($expected, $signature)) {
    http_response_code(403); echo json_encode(['ok' => false]); exit;
}
$request = json_decode($body, true);
if (($request['action'] ?? '') === 'health') {
    echo json_encode(['ok' => true, 'version' => 'selection-mail-worker-1']); exit;
}
function mail_ack(array $item, string $outcome, array $extra = []): array {
    return machine_api('/candidate/bridge/mail/ack', array_merge($extra,
        ['id' => $item['id'], 'lease' => $item['lease'], 'outcome' => $outcome]));
}
try {
    $claim = machine_api('/candidate/bridge/mail/claim', []);
    if (empty($claim['ok'])) { throw new RuntimeException('Queue unavailable.'); }
    $item = $claim['item'] ?? null;
    if ($item === null) { echo json_encode(['ok' => true, 'processed' => 0]); exit; }
    $started = mail_ack($item, 'started');
    if (empty($started['ok'])) { throw new RuntimeException('Unable to start the delivery.'); }
    try {
        send_selection_email($item['to'], $item['subject'], $item['body'], $item['message_id']);
    } catch (MailTransportException $error) {
        mail_ack($item, $error->uncertain ? 'uncertain' : 'failed',
            ['error' => $error->getMessage(), 'permanent' => $error->permanent]);
        echo json_encode(['ok' => true, 'processed' => 1, 'result' => $error->uncertain ? 'uncertain' : 'failed']); exit;
    }
    $acknowledged = false;
    for ($attempt = 0; $attempt < 3; $attempt++) {
        try { $ack = mail_ack($item, 'sent'); $acknowledged = !empty($ack['ok']); } catch (Throwable $ignored) {}
        if ($acknowledged) { break; }
        usleep(200000);
    }
    if (!$acknowledged) { throw new RuntimeException('Email accepted; acknowledgement pending.'); }
    echo json_encode(['ok' => true, 'processed' => 1, 'result' => 'sent']);
} catch (Throwable $error) {
    http_response_code(503);
    // Transport diagnostics only; no recipient, message, credential or token.
    echo json_encode(['ok' => false, 'message' => 'Selection mail worker temporarily unavailable.']);
}
