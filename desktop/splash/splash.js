const error = new URLSearchParams(location.search).get("error");
if (error) {
  const status = document.getElementById("status");
  status.textContent = error;
  status.classList.add("error");
  document.getElementById("spinner").hidden = true;

  const restart = document.getElementById("restart");
  restart.hidden = false;
  restart.addEventListener("click", () => {
    restart.disabled = true;
    window.__TAURI__.core.invoke("restart_app");
  });
}
