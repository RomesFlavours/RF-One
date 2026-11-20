// History only. Rule authoring and application choices live in the conversation.
(function () {
  "use strict";
  function element(tag, text) { var e = document.createElement(tag); e.textContent = text; return e; }
  function post(url, body) {
    return fetch(url, {method: "POST", body: body, credentials: "same-origin", headers: {Accept: "application/json"}})
      .then(function (response) { return response.json().then(function (data) {
        if (!response.ok || !data.ok) { throw new Error(data.error || "Rollback could not be completed."); }
        return data;
      }); });
  }
  document.querySelectorAll(".application-rollback-form").forEach(function (rollbackForm) {
    rollbackForm.addEventListener("submit", function (event) {
      event.preventDefault(); var button = rollbackForm.querySelector("button"), out = rollbackForm.parentElement.querySelector(".rollback-result");
      if (button.disabled) { return; } button.disabled = true;
      post(rollbackForm.action, new FormData(rollbackForm)).then(function (data) {
        out.textContent = data.restored + " transactions restored. " + data.skipped.length + " unchanged because they were edited later.";
        data.skipped.forEach(function (item) { out.appendChild(element("span", " Transaction #" + item.id + ": later change preserved.")); });
      }).catch(function (error) { button.disabled = false; out.textContent = error.message; });
    });
  });
})();
