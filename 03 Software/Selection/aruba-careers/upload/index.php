<?php
/*
 * RF-One Selection — careers page on Aruba (SELECTION_ARUBA_IDENTITY_001).
 *
 * Step 1: First Name, Last Name, Email -> Receive Code (a 5-digit code is
 * emailed from the company mailbox). Step 2: "Welcome, <First Name>!" ->
 * Verification Code -> Confirm or Cancel, without asking the details again.
 * After the right code, one signed single-use token is posted (form body,
 * HTTPS) to Selection on AWS, which opens the candidate's application for
 * the position. The URL only ever carries the position's public token.
 */

declare(strict_types=1);

define('RFC_APP', true);
require __DIR__ . '/private/lib.php';

header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
header('X-Robots-Tag: noindex, nofollow');
header('Cache-Control: no-store');
header('X-Frame-Options: DENY');

function rfc_page(string $title, string $content, ?array $config = null): void
{
    $company = rfc_h($config['company_name'] ?? "Rome's Flavours");
    echo '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        . '<meta name="viewport" content="width=device-width, initial-scale=1">'
        . '<title>' . rfc_h($title) . ' · ' . $company . '</title>'
        . '<link rel="stylesheet" href="assets/careers.css?v=1">'
        . '<script defer src="assets/careers.js?v=1"></script></head>'
        . '<body class="public"><div class="wrap"><header class="site-header"><span class="brand">'
        . '<span class="brand-name-group"><span class="brand-wordmark">' . $company . '</span>'
        . '<span class="brand-suffix">Careers</span></span></span></header>'
        . $content . '</div></body></html>';
}

function rfc_flash(string $kind, string $text): void
{
    $_SESSION['flash'] = ['kind' => $kind, 'text' => $text];
}

function rfc_take_flash(): string
{
    if (empty($_SESSION['flash'])) {
        return '';
    }
    $flash = $_SESSION['flash'];
    unset($_SESSION['flash']);
    $class = $flash['kind'] === 'error' ? 'error' : 'info';
    return '<div class="' . $class . '" role="status">' . rfc_h($flash['text']) . '</div>';
}

function rfc_self(): string
{
    $position = (string)($_SESSION['position'] ?? '');
    // Always the page itself (…/index.php): it does not depend on IIS's default documents.
    $path = rfc_base_path() . basename((string)($_SERVER['SCRIPT_NAME'] ?? 'index.php'));
    return $path . ($position !== '' ? '?' . http_build_query(['position' => $position]) : '');
}

function rfc_back(): void
{
    header('Location: ' . rfc_self(), true, 303);
    exit;
}

/** Issues and emails a new code for the details in the session flow. */
function rfc_send_code(array &$flow): bool
{
    $ip = rfc_client_ip();
    $refusal = rfc_send_refusal($flow['email'], $ip);
    if ($refusal !== null) {
        rfc_log('code_refused_limit', ['email' => rfc_pseudonym($flow['email']), 'ip' => rfc_pseudonym($ip)]);
        rfc_flash('error', $refusal);
        return false;
    }
    rfc_record_send($flow['email'], $ip);
    $code = rfc_new_code();
    try {
        rfc_send_code_email($flow['email'], $flow['first'], $code);
    } catch (RfcSendError $e) {
        rfc_log('code_not_sent', ['email' => rfc_pseudonym($flow['email']), 'reason' => substr($e->getMessage(), 0, 60)]);
        rfc_flash('error', 'We could not send the verification email. Please check the address or try again later.');
        return false;
    }
    $flow['code_hash'] = rfc_hash_code($code, $flow['email']);
    $flow['expires'] = time() + RFC_CODE_TTL;
    $flow['attempts'] = 0;
    unset($code);
    rfc_log('code_sent', ['email' => rfc_pseudonym($flow['email']), 'ip' => rfc_pseudonym($ip),
                          'position' => $flow['position']]);
    rfc_flash('info', 'We sent a 5-digit code to ' . $flow['email'] . '. It expires in 10 minutes.');
    return true;
}

// ---------------------------------------------------------------------------

try {
    $config = rfc_config();
} catch (RfcConfigError $e) {
    http_response_code(503);
    error_log('RF-One careers page: configuration problem: ' . $e->getMessage());
    rfc_page('Temporarily unavailable', '<div class="card"><h1>Temporarily unavailable</h1>'
        . '<p>Email verification is not available right now. Please try again later.</p></div>');
    exit;
}

if ($config['require_https'] && !rfc_is_https()) {
    $query = (string)($_SERVER['QUERY_STRING'] ?? '');
    header('Location: https://' . ($_SERVER['HTTP_HOST'] ?? '') . (string)($_SERVER['SCRIPT_NAME'] ?? '/')
        . ($query !== '' ? '?' . $query : ''), true, 301);
    exit;
}
if ($config['require_https']) {
    header('Strict-Transport-Security: max-age=31536000');
}
$selectionOrigin = preg_replace('#^(https?://[^/]+).*$#', '$1', $config['selection_handoff_url']);
header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    . "base-uri 'none'; frame-ancestors 'none'; form-action 'self' " . $selectionOrigin);

rfc_start_session();

// The position comes from the job posting link; a different position starts over.
$requested = (string)($_GET['position'] ?? '');
if ($requested !== '' && rfc_valid_position($requested) && $requested !== ($_SESSION['position'] ?? '')) {
    $_SESSION['position'] = $requested;
    unset($_SESSION['flow']);
}
$position = (string)($_SESSION['position'] ?? '');
$flow = isset($_SESSION['flow']) && is_array($_SESSION['flow']) ? $_SESSION['flow'] : null;

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    if (!rfc_csrf_ok()) {
        rfc_flash('error', 'Your session expired. Please try again.');
        rfc_back();
    }
    $action = (string)($_POST['action'] ?? '');

    if ($action === 'request_code') {
        $first = rfc_clean_name((string)($_POST['first_name'] ?? ''));
        $last = rfc_clean_name((string)($_POST['last_name'] ?? ''));
        $email = rfc_clean_email((string)($_POST['email'] ?? ''));
        $_SESSION['draft'] = ['first' => $first, 'last' => $last, 'email' => (string)($_POST['email'] ?? '')];
        if ($position === '') {
            rfc_flash('error', 'Please open this page from the job posting you want to apply for.');
        } elseif ($first === '' || $last === '') {
            rfc_flash('error', 'Please enter your first and last name.');
        } elseif ($email === '') {
            rfc_flash('error', 'Please enter a valid email address.');
        } else {
            $new = ['first' => $first, 'last' => $last, 'email' => $email, 'position' => $position];
            if (rfc_send_code($new)) {
                session_regenerate_id(true);
                $_SESSION['flow'] = $new;
                unset($_SESSION['draft']);
            }
        }
        rfc_back();
    }

    if ($action === 'resend' && $flow !== null) {
        if (rfc_send_code($flow)) {
            $_SESSION['flow'] = $flow;
        }
        rfc_back();
    }

    if ($action === 'cancel') {
        unset($_SESSION['flow'], $_SESSION['draft']);
        rfc_flash('info', 'Verification cancelled.');
        rfc_back();
    }

    if ($action === 'confirm' && $flow !== null) {
        $ip = rfc_client_ip();
        $code = preg_replace('/\D/', '', (string)($_POST['code'] ?? ''));
        if (empty($flow['code_hash'])) {
            rfc_flash('error', 'This code is no longer valid. Please ask for a new code.');
            rfc_back();
        }
        if ($flow['expires'] <= time()) {
            $flow['code_hash'] = null;
            $_SESSION['flow'] = $flow;
            rfc_flash('error', 'This code has expired. Please ask for a new code.');
            rfc_back();
        }
        if (rfc_too_many_failures($ip)) {
            rfc_flash('error', 'Too many wrong attempts from this network. Please try again later.');
            rfc_back();
        }
        if (strlen($code) !== RFC_CODE_LENGTH || !hash_equals($flow['code_hash'], rfc_hash_code($code, $flow['email']))) {
            rfc_record_failure($ip);
            $flow['attempts']++;
            $left = RFC_MAX_ATTEMPTS - $flow['attempts'];
            if ($left <= 0) {
                $flow['code_hash'] = null;
                rfc_flash('error', 'Too many wrong attempts. Please ask for a new code.');
            } else {
                rfc_flash('error', 'The code is not correct. ' . $left . ' attempt' . ($left === 1 ? '' : 's') . ' left.');
            }
            rfc_log('code_wrong', ['email' => rfc_pseudonym($flow['email']), 'ip' => rfc_pseudonym($ip),
                                   'left' => max(0, $left)]);
            $_SESSION['flow'] = $flow;
            rfc_back();
        }
        // Right code: it is used up, the session forgets the flow, and Selection receives the identity.
        $token = rfc_issue_token($flow['first'], $flow['last'], $flow['email'], $flow['position']);
        rfc_log('verified', ['email' => rfc_pseudonym($flow['email']), 'position' => $flow['position']]);
        unset($_SESSION['flow'], $_SESSION['draft']);
        session_regenerate_id(true);
        rfc_page('Opening your application',
            '<div class="card"><h1>Email confirmed</h1><p class="waiting">Opening your application…</p>'
            . '<form id="handoff" method="post" action="' . rfc_h($config['selection_handoff_url']) . '">'
            . '<input type="hidden" name="identity_token" value="' . rfc_h($token) . '">'
            . '<p><button type="submit" class="btn">Continue to your application</button></p></form></div>',
            $config);
        exit;
    }
    rfc_back();
}

// ---------------------------------------------------------------------------
// Pages
// ---------------------------------------------------------------------------

$csrf = rfc_h(rfc_csrf_token());
$flash = rfc_take_flash();

if ($flow !== null) {
    $active = !empty($flow['code_hash']) && $flow['expires'] > time();
    $content = '<div class="card"><h1>Welcome, ' . rfc_h($flow['first']) . '!</h1>' . $flash
        . '<p class="muted">Enter the 5-digit code we sent to <b>' . rfc_h($flow['email']) . '</b>.</p>';
    if ($active) {
        $content .= '<form method="post" class="busy-form" autocomplete="off">'
            . '<input type="hidden" name="csrf" value="' . $csrf . '">'
            . '<label for="code">Verification Code</label>'
            . '<input type="text" id="code" name="code" inputmode="numeric" pattern="[0-9]{5}" maxlength="5" '
            . 'autocomplete="one-time-code" required autofocus>'
            . '<div class="row actions"><button type="submit" name="action" value="confirm" class="btn">Confirm</button>'
            . '<button type="submit" name="action" value="cancel" class="btn btn-secondary" formnovalidate>Cancel</button></div>'
            . '</form>';
    } else {
        $content .= '<form method="post" class="row actions"><input type="hidden" name="csrf" value="' . $csrf . '">'
            . '<button type="submit" name="action" value="cancel" class="btn btn-secondary">Cancel</button></form>';
    }
    $content .= '<form method="post" class="resend"><input type="hidden" name="csrf" value="' . $csrf . '">'
        . '<button type="submit" name="action" value="resend" class="link-button">Send a new code</button></form></div>';
    rfc_page('Verify your email', $content, $config);
    exit;
}

$draft = isset($_SESSION['draft']) && is_array($_SESSION['draft']) ? $_SESSION['draft'] : [];
$content = '<div class="card"><h1>Apply</h1>' . $flash;
if ($position === '') {
    $content .= '<p>Please open this page from the job posting you want to apply for.</p></div>';
    rfc_page('Apply', $content, $config);
    exit;
}
$content .= '<p class="muted">Confirm your email to start or continue your application. '
    . 'We will send you a 5-digit code. No password is needed.</p>'
    . '<form method="post" class="busy-form">'
    . '<input type="hidden" name="csrf" value="' . $csrf . '">'
    . '<label for="first_name">First Name</label>'
    . '<input type="text" id="first_name" name="first_name" autocomplete="given-name" maxlength="120" required value="' . rfc_h($draft['first'] ?? '') . '">'
    . '<label for="last_name">Last Name</label>'
    . '<input type="text" id="last_name" name="last_name" autocomplete="family-name" maxlength="120" required value="' . rfc_h($draft['last'] ?? '') . '">'
    . '<label for="email">Email</label>'
    . '<input type="email" id="email" name="email" autocomplete="email" maxlength="254" required value="' . rfc_h($draft['email'] ?? '') . '">'
    . '<div class="row actions"><button type="submit" name="action" value="request_code" class="btn">Receive Code</button></div>'
    . '</form></div>';
rfc_page('Apply', $content, $config);
