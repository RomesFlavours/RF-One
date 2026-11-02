/* Speech/text share the same session. No audio uploads or implicit submission. */
(() => {
  'use strict';
  const root = document.getElementById('interview');
  if (!root) return;
  const transcript = document.getElementById('interview-transcript');
  const input = document.getElementById('interview-message');
  const error = document.getElementById('interview-error');
  const voiceStatus = document.getElementById('interview-voice-status');
  const mic = document.getElementById('interview-microphone');
  const stopMic = document.getElementById('interview-stop-microphone');
  const listen = document.getElementById('interview-listen');
  const stopSpeech = document.getElementById('interview-stop-speech');
  const question = document.getElementById('interview-question');
  const progress = document.getElementById('interview-progress');
  const saveStatus = document.getElementById('interview-save-status');
  const autoSpeak = document.getElementById('interview-auto-speak');
  const completeButton = document.querySelector('#interview-complete button');
  const synth = window.speechSynthesis;
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = Recognition ? new Recognition() : null;
  let busy = false;
  let listening = false;
  let baseText = '';
  let answerCount = transcript.querySelectorAll('.interview-message-user').length;
  let speakWhenReady = false;

  function showError(message) { error.textContent = message; error.hidden = false; }
  function stopAudio() { if (synth) synth.cancel(); }
  function speak() {
    if (!synth || !window.SpeechSynthesisUtterance) return;
    if (recognition && listening) {
      speakWhenReady = true; recognition.stop(); return;
    }
    stopAudio();
    if (!question.textContent.trim()) return;
    const utterance = new SpeechSynthesisUtterance(question.textContent);
    utterance.lang = 'en-US';
    utterance.onerror = event => {
      if (!['canceled', 'interrupted'].includes(event.error)) {
        voiceStatus.textContent = 'Speech playback failed. Retry or read the question above.';
      }
    };
    synth.speak(utterance);
  }
  function draw(messages) {
    transcript.replaceChildren();
    for (const message of messages) {
      const section = document.createElement('section');
      section.className = `interview-message interview-message-${message.role}`;
      const heading = document.createElement('h2');
      heading.textContent = message.role === 'user' ? 'You' : 'AI';
      const body = document.createElement('p');
      body.style.whiteSpace = 'pre-wrap';
      body.textContent = message.text;
      section.append(heading, body); transcript.append(section);
    }
    question.textContent = messages.length ? messages[messages.length - 1].text : '';
    answerCount = messages.filter(message => message.role === 'user').length;
    document.getElementById('interview-answer-count').textContent = `(${answerCount} answers saved)`;
    progress.textContent = `${answerCount} answers saved. Your next question is ready.`;
  }
  completeButton.disabled = answerCount === 0;
  listen.disabled = !synth;
  stopSpeech.disabled = !synth;
  autoSpeak.disabled = !synth;
  if (!synth) autoSpeak.checked = false;
  autoSpeak.addEventListener('change', () => { if (!autoSpeak.checked) stopAudio(); });
  input.addEventListener('input', () => {
    saveStatus.textContent = input.value.trim() ? 'Not sent yet. Review your answer before sending.' : 'All submitted answers are saved.';
  });
  listen.addEventListener('click', speak);
  stopSpeech.addEventListener('click', stopAudio);
  if (recognition) {
    recognition.lang = 'en-US';
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.onstart = () => {
      listening = true; mic.disabled = true; stopMic.disabled = false;
      voiceStatus.textContent = 'Listening. When finished, review the text and send it.';
    };
    recognition.onresult = event => {
      const parts = [];
      for (let i = 0; i < event.results.length; i++) if (event.results[i].isFinal) parts.push(event.results[i][0].transcript);
      input.value = [baseText, ...parts].filter(Boolean).join(' ');
      saveStatus.textContent = 'Not sent yet. Review your answer before sending.';
      document.getElementById('interview-channel').value = 'voice';
    };
    recognition.onerror = event => {
      voiceStatus.textContent = event.error === 'not-allowed'
        ? 'Microphone access was denied. Enable it in your browser settings to speak.'
        : 'Dictation is unavailable. You can still edit the text already recognized.';
    };
    recognition.onend = () => {
      listening = false; mic.disabled = busy; stopMic.disabled = true;
      if (speakWhenReady) { speakWhenReady = false; speak(); }
    };
    mic.addEventListener('click', () => {
      stopAudio(); baseText = input.value.trim();
      try { recognition.start(); } catch (_) { voiceStatus.textContent = 'Could not start the microphone. Please try again.'; }
    });
    stopMic.addEventListener('click', () => recognition.stop());
  } else {
    mic.disabled = true;
    voiceStatus.textContent = 'This browser does not support dictation. Open the interview in a compatible browser to use voice input.';
  }
  for (const form of document.querySelectorAll('.interview-action')) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy) return;
      if (form.id === 'interview-complete' && input.value.trim()) {
        showError('You have an unsent answer. Send or clear it before completing the interview.'); return;
      }
      if (listening) { showError('Stop dictation and review the text before sending it.'); return; }
      stopAudio(); error.hidden = true;
      const data = new FormData(form);
      busy = true;
      input.readOnly = true;
      root.setAttribute('aria-busy', 'true');
      progress.textContent = form.id === 'interview-complete'
        ? 'Preparing your interview results…' : 'Preparing the next question…';
      saveStatus.textContent = form.id === 'interview-answer' ? 'Sending your answer…' : '';
      const submits = [...root.querySelectorAll('button[type="submit"]')];
      submits.forEach(button => { button.disabled = true; });
      mic.disabled = true;
      try {
        const response = await fetch(window.location.href, {
          method: 'POST', body: data, headers: { Accept: 'application/json' }
        });
        if (!response.headers.get('content-type')?.includes('application/json')) {
          // A gateway timeout or restart answers with an HTML page, not our JSON.
          if ([502, 503, 504].includes(response.status)) {
            throw new Error('The AI took too long to answer. Please try again; your unsent answer is still here.');
          }
          throw new Error('Your session is unavailable. Reload the page or sign in again; keep a copy of your unsent answer.');
        }
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'The operation failed. Please try again.');
        if (result.status === 'COMPLETED') { window.location.assign(result.redirect); return; }
        root.querySelectorAll('input[name="revision"]').forEach(field => { field.value = result.revision; });
        document.getElementById('interview-start').hidden = true;
        document.getElementById('interview-intro').hidden = true;
        document.getElementById('interview-conversation').hidden = false;
        root.dataset.status = result.status;
        document.getElementById('interview-state').textContent = 'In progress';
        draw(result.messages); input.value = '';
        document.getElementById('interview-channel').value = 'text';
        voiceStatus.textContent = 'The question is ready. Speak or type your answer.';
        saveStatus.textContent = 'All submitted answers are saved.';
        if (autoSpeak.checked) speak();
        input.focus();
      } catch (err) {
        showError(err.message);
        progress.textContent = 'This request did not complete. Reload if the interview changed elsewhere.';
        saveStatus.textContent = 'Your unsent answer is still here.';
      }
      finally {
        busy = false; submits.forEach(button => { button.disabled = false; });
        completeButton.disabled = answerCount === 0;
        input.readOnly = false;
        root.setAttribute('aria-busy', 'false');
        mic.disabled = !recognition;
      }
    });
  }
  window.addEventListener('pagehide', () => { stopAudio(); if (recognition) recognition.abort(); });
  window.addEventListener('beforeunload', event => {
    if (input.value.trim() || busy) { event.preventDefault(); event.returnValue = ''; }
  });
})();
