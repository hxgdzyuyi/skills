(() => {
  "use strict";

  const root = document.getElementById("js_content");
  const button = document.getElementById("mp-copy-button");
  const status = document.getElementById("mp-copy-status");
  if (!root || !button || !status) return;

  const styleProperties = [
    "display",
    "position",
    "width",
    "max-width",
    "min-width",
    "height",
    "max-height",
    "min-height",
    "margin",
    "padding",
    "box-sizing",
    "overflow",
    "overflow-x",
    "overflow-y",
    "color",
    "background",
    "background-color",
    "border",
    "border-radius",
    "box-shadow",
    "opacity",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "line-height",
    "letter-spacing",
    "text-align",
    "text-decoration",
    "text-indent",
    "text-transform",
    "white-space",
    "word-break",
    "overflow-wrap",
    "vertical-align",
    "list-style",
    "list-style-position",
    "list-style-type",
    "border-collapse",
    "border-spacing",
    "justify-content",
    "align-items",
    "align-self",
    "transform"
  ];

  function inlineComputedStyles(source, clone) {
    const sourceElements = Array.from(source.querySelectorAll("*"));
    const cloneElements = Array.from(clone.querySelectorAll("*"));
    sourceElements.forEach((sourceElement, index) => {
      const cloneElement = cloneElements[index];
      if (!cloneElement) return;
      const computed = window.getComputedStyle(sourceElement);
      styleProperties.forEach((property) => {
        const value = computed.getPropertyValue(property);
        if (value) cloneElement.style.setProperty(property, value);
      });
      cloneElement.removeAttribute("id");
      cloneElement.removeAttribute("class");
      cloneElement.removeAttribute("contenteditable");
    });
  }

  function blobToDataURL(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error || new Error("FileReader failed"));
      reader.readAsDataURL(blob);
    });
  }

  async function inlineImages(source, clone) {
    const sourceImages = Array.from(source.querySelectorAll("img"));
    const cloneImages = Array.from(clone.querySelectorAll("img"));
    const failures = [];

    await Promise.all(sourceImages.map(async (sourceImage, index) => {
      const cloneImage = cloneImages[index];
      if (!cloneImage) return;
      const imageURL = sourceImage.currentSrc || sourceImage.src;
      if (!imageURL || imageURL.startsWith("data:")) return;
      try {
        const response = await fetch(imageURL);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        cloneImage.src = await blobToDataURL(await response.blob());
        cloneImage.removeAttribute("srcset");
      } catch (error) {
        failures.push(sourceImage.getAttribute("src") || imageURL);
      }
    }));

    return failures;
  }

  async function serialize() {
    const container = document.createElement("section");
    container.innerHTML = root.innerHTML;
    inlineComputedStyles(root, container);
    const failures = await inlineImages(root, container);
    return {
      html: container.innerHTML,
      text: container.textContent || "",
      failures
    };
  }

  function fallbackCopy(html) {
    const temporary = document.createElement("section");
    temporary.innerHTML = html;
    temporary.setAttribute("contenteditable", "true");
    temporary.style.position = "fixed";
    temporary.style.left = "-10000px";
    temporary.style.top = "0";
    document.body.appendChild(temporary);

    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(temporary);
    selection.removeAllRanges();
    selection.addRange(range);
    const copied = document.execCommand("copy");
    selection.removeAllRanges();
    temporary.remove();
    if (!copied) throw new Error("浏览器拒绝复制");
  }

  async function copyArticle() {
    button.disabled = true;
    status.textContent = "正在整理内联样式和图片...";
    try {
      const payload = await serialize();
      if (
        navigator.clipboard &&
        navigator.clipboard.write &&
        typeof ClipboardItem !== "undefined"
      ) {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/html": new Blob([payload.html], { type: "text/html" }),
            "text/plain": new Blob([payload.text], { type: "text/plain" })
          })
        ]);
      } else {
        fallbackCopy(payload.html);
      }

      status.textContent = payload.failures.length
        ? `正文已复制；${payload.failures.length} 张图片转换失败，请在公众号素材库中替换。`
        : "正文已复制，可粘贴到微信公众号编辑器。";
    } catch (error) {
      status.textContent = `复制失败：${error.message || error}`;
    } finally {
      button.disabled = false;
    }
  }

  button.addEventListener("click", copyArticle);
  window.mpArticleCopy = { serialize };
})();
