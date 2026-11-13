<?php
declare(strict_types=1);
define('RFONE_ENTRY', true);
header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('X-Robots-Tag: noindex, nofollow');
$host = strtolower(explode(':', $_SERVER['HTTP_HOST'] ?? '')[0]);
if (!in_array($host, ['rmaed.it', 'www.rmaed.it'], true)) { http_response_code(403); exit; }
if (empty($_SERVER['HTTPS']) || strtolower((string)$_SERVER['HTTPS']) === 'off') {
    header('Location: https://www.rmaed.it/index.php', true, 302); exit;
}
ini_set('display_errors', '0');
session_name('rfone_selection_aruba');
session_start(['cookie_secure' => true, 'cookie_httponly' => true, 'cookie_samesite' => 'Lax', 'use_strict_mode' => true]);
require __DIR__ . '/relay.php';
// A visit to the domain starts a fresh attempt. The explicit index.php
// URL keeps the in-progress verification when its form is submitted.
if ($_SERVER['REQUEST_METHOD'] === 'GET' &&
    (isset($_GET['start']) || parse_url($_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH) === '/')) {
    $_SESSION = [];
    session_regenerate_id(true);
    header('Location: ' . $config['aws_base'] . '/candidate/bridge/start', true, 302);
    exit;
}
if ($_SERVER['REQUEST_METHOD'] === 'GET' && isset($_GET['state'])) {
    $state = (string)$_GET['state'];
    if (strlen($state) > 1024 || !preg_match('/^[A-Za-z0-9_.-]+$/D', $state)) { http_response_code(400); exit; }
    session_regenerate_id(true);
    $_SESSION = ['bridge_state' => $state, 'started' => time(), 'csrf' => bin2hex(random_bytes(32))];
    header('Location: /index.php', true, 303); exit;
}
if (empty($_SESSION['bridge_state']) || time() - (int)($_SESSION['started'] ?? 0) > 1700) {
    header('Location: ' . $config['aws_base'] . '/candidate/bridge/start', true, 302); exit;
}
$error = ''; $notice = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!hash_equals($_SESSION['csrf'], (string)($_POST['csrf'] ?? ''))) { http_response_code(400); exit('Please reload the page.'); }
    $action = (string)($_POST['action'] ?? '');
    try {
        if ($action === 'code') {
            if (time() - (int)($_SESSION['last_send'] ?? 0) < 60) { throw new RuntimeException('Please wait one minute before requesting another code.'); }
            $result = relay(['action' => 'code', 'full_name' => (string)($_POST['full_name'] ?? ''),
                'email' => (string)($_POST['email'] ?? '')]);
            if (empty($result['ok'])) { throw new RuntimeException((string)($result['message'] ?? 'Unable to send your code.')); }
            $_SESSION['email'] = $result['email'];
            try { deliver_code($result['email'], $result['delivery_code']); }
            catch (Throwable $sendError) {
                try { relay(['action' => 'withdraw', 'email' => $result['email']]); } catch (Throwable $ignored) {}
                unset($_SESSION['email']);
                throw $sendError;
            }
            $_SESSION['last_send'] = time();
            $notice = 'We sent a 6-digit code to your email address. It expires in 10 minutes.';
        } elseif ($action === 'confirm') {
            $result = relay(['action' => 'confirm', 'email' => $_SESSION['email'] ?? '', 'code' => (string)($_POST['code'] ?? '')]);
            if (empty($result['ok'])) { throw new RuntimeException((string)($result['message'] ?? 'Please check your code.')); }
            finish_on_aws($result['redirect']);
        } elseif ($action === 'cancel') {
            relay(['action' => 'withdraw', 'email' => $_SESSION['email'] ?? '']);
            unset($_SESSION['email']);
        }
    } catch (Throwable $ex) { $error = $ex->getMessage(); }
}
function e(string $value): string { return htmlspecialchars($value, ENT_QUOTES, 'UTF-8'); }
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RF-One Selection · Candidate access</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#1e3044;font:16px system-ui,sans-serif}main{max-width:620px;margin:50px auto;padding:32px;background:white;border:1px solid #dce3ea;border-radius:18px}h1{margin:20px 0 12px;font-size:34px}p{line-height:1.65;color:#536477}label{display:block;margin:18px 0 7px;font-weight:600}input{width:100%;padding:13px;border:1px solid #afbdca;border-radius:7px;font:inherit}button{background:#163e64;color:white;border:0;border-radius:7px;padding:13px 20px;font:inherit;cursor:pointer;margin-top:22px}.secondary{background:#edf1f5;color:#163e64}.error,.notice{padding:15px;line-height:1.6;border-radius:7px}.error{background:#fff0ee;color:#8a271e}.notice{background:#eaf6ef;color:#205b3c}summary{cursor:pointer;font-weight:600;margin-top:30px}.brand{font-size:15px;font-weight:750;letter-spacing:1px}.small{font-size:13px}@media(max-width:650px){main{margin:16px;padding:23px}}</style></head><body><main>
<div class="brand">RF-ONE / SELECTION</div><h1>Your application starts here</h1>
<p>Confirm your email, then continue to upload your résumé and complete the first interview.</p>
<?php if ($error): ?><p class="error" role="alert"><?=e($error)?></p><?php endif; ?>
<?php if ($notice): ?><p class="notice" role="status"><?=e($notice)?></p><?php endif; ?>
<?php if (!empty($_SESSION['email'])): ?>
<form method="post"><input type="hidden" name="csrf" value="<?=e($_SESSION['csrf'])?>"><input type="hidden" name="action" value="confirm">
<p>Code sent to <strong><?=e($_SESSION['email'])?></strong></p><label for="code">Verification code</label>
<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required autofocus>
<button>Confirm and continue</button></form>
<form method="post"><input type="hidden" name="csrf" value="<?=e($_SESSION['csrf'])?>"><button class="secondary" name="action" value="cancel">Cancel / request a new code</button></form>
<?php else: ?>
<form method="post"><input type="hidden" name="csrf" value="<?=e($_SESSION['csrf'])?>"><input type="hidden" name="action" value="code">
<label for="name">Full name</label><input id="name" name="full_name" autocomplete="name" maxlength="255" required>
<label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" maxlength="320" required>
<button>Receive code by email</button></form>
<?php endif; ?><p class="small">RF-One Selection · Candidate access</p></main></body></html>
