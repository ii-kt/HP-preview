const demoForm = document.querySelector("[data-demo-form]");
const formNote = document.querySelector("[data-form-note]");

if (demoForm && formNote) {
  demoForm.addEventListener("submit", (event) => {
    event.preventDefault();

    const formData = new FormData(demoForm);
    const name = String(formData.get("name") || "").trim();
    const displayName = name ? `${name}様` : "お客様";

    formNote.textContent = `${displayName}、ありがとうございます。これは制作サンプルのため送信は行わず、実運用時はメールや予約フォームへ接続できます。`;
    formNote.classList.add("is-complete");
  });
}
