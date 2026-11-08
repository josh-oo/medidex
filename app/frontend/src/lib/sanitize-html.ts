// HTML from outside (the abstract of an uploaded bibliography or a register) is untrusted: only plain formatting is kept.
// What can run or load something goes with its content, any other element is replaced by its content (e.g. the <jats:p> of
// Crossref). Kept elements lose their attributes, except the data-* attributes of a <mark> (inert, for annotations).
const KEPT_ELEMENTS = new Set(["B", "STRONG", "I", "EM", "U", "SUB", "SUP", "SMALL", "P", "BR", "SPAN", "DIV", "UL", "OL", "LI", "H1", "H2", "H3", "H4", "H5", "H6", "MARK"]);
const DROPPED_ELEMENTS = new Set(["SCRIPT", "STYLE", "IFRAME", "FRAME", "OBJECT", "EMBED", "TEMPLATE", "NOSCRIPT", "SVG", "MATH", "LINK", "META", "BASE", "FORM", "INPUT", "BUTTON", "TEXTAREA", "SELECT", "TITLE", "IMG", "VIDEO", "AUDIO", "SOURCE"]);

function sanitizeNode(parent: Node): void {
  for (const child of [...parent.childNodes]) {
    if (child.nodeType === Node.TEXT_NODE) continue;
    if (child.nodeType !== Node.ELEMENT_NODE) {
      child.remove(); // comments, processing instructions
      continue;
    }
    const element = child as Element;
    const name = element.tagName.toUpperCase();
    if (DROPPED_ELEMENTS.has(name)) {
      element.remove();
      continue;
    }
    sanitizeNode(element);
    if (KEPT_ELEMENTS.has(name)) {
      for (const attribute of [...element.attributes]) {
        if (!(name === "MARK" && attribute.name.startsWith("data-"))) element.removeAttribute(attribute.name);
      }
    } else {
      element.replaceWith(...element.childNodes);
    }
  }
}

/** The HTML with only its plain formatting (see KEPT_ELEMENTS); parsed in an inert document, so nothing of it runs. */
export function sanitizeHtml(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  sanitizeNode(doc.body);
  return doc.body.innerHTML;
}
