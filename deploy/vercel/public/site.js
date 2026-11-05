// Shared by the home page, /skola and /bygg. ?demo opens the page's video, which
// is what the links in posts rely on (/video redirects to /?demo=en).
(() => {
  const dialog = document.querySelector("#video-dialog");
  if (dialog) {
    const video = dialog.querySelector("video");
    const params = new URLSearchParams(location.search);
    const open = (src, poster) => {
      if (video.getAttribute("src") !== src) {
        video.src = src;
        video.poster = poster || "";
      }
      if (!dialog.open) dialog.showModal();
      video.play().catch((err) => {
        // Only a blocked autoplay gets a muted retry: closing the dialog also
        // rejects this promise, and a retry would keep playing behind the page.
        if (err.name !== "NotAllowedError" || !dialog.open) return;
        video.muted = true;
        video.play().catch(() => {});
      });
    };
    const openDefault = () => open(document.body.dataset.video, document.body.dataset.poster);

    for (const el of document.querySelectorAll("[data-video]")) {
      if (el === document.body) continue;
      el.addEventListener("click", () => el.dataset.video === "default"
        ? openDefault()
        : open(el.dataset.video, el.dataset.poster));
    }
    dialog.querySelector(".close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
    dialog.addEventListener("close", () => {
      video.pause();
      if (params.has("demo")) history.replaceState(null, "", location.pathname + location.hash);
    });
    if (params.has("demo")) openDefault();
  }

  for (const button of document.querySelectorAll("[data-copy]")) {
    button.addEventListener("click", async () => {
      const label = button.textContent;
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        button.textContent = button.dataset.done;
        setTimeout(() => { button.textContent = label; }, 1600);
      } catch {
        // No clipboard access: the command is still there to select by hand.
      }
    });
  }
})();
