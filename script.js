const demoSubmitButton = document.querySelector("[data-demo-submit]");
const formNote = document.querySelector("[data-form-note]");

if (demoSubmitButton && formNote) {
  demoSubmitButton.addEventListener("click", () => {
    formNote.textContent = "デモページのため、送信処理は行われません。";
  });
}
