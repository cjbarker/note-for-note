// Client-side export of the engraved score to SVG / PNG / PDF, reproducing what
// OSMD renders on screen (WYSIWYG). The jsPDF + svg2pdf.js libraries are imported
// dynamically so they only load on first export, keeping the initial bundle light.
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { downloadBlob } from "./lib/download";

// Render MusicXML into a hidden, off-screen OSMD instance and return its
// container so the caller can pull out the produced <svg>/<canvas> nodes.
// The container is positioned off-screen with a real width — `display:none`
// would give OSMD a zero width and break its layout.
async function renderHidden(
  musicXml: string,
  opts: { backend: "svg" | "canvas"; pageFormat?: string; zoom?: number }
): Promise<HTMLDivElement> {
  const container = document.createElement("div");
  container.style.position = "fixed";
  container.style.left = "-10000px";
  container.style.top = "0";
  container.style.width = "1200px";
  document.body.appendChild(container);

  const osmd = new OpenSheetMusicDisplay(container, {
    autoResize: false,
    backend: opts.backend,
    drawTitle: false,
    pageFormat: opts.pageFormat,
  });
  if (opts.zoom) osmd.zoom = opts.zoom;
  await osmd.load(musicXml);
  if (opts.pageFormat) osmd.setPageFormat(opts.pageFormat);
  osmd.render();
  return container;
}

// SVG: serialize an already-rendered on-screen <svg>. Vector and exact.
export function exportSvg(svgEl: SVGElement, filename = "transcription.svg") {
  const xml = new XMLSerializer().serializeToString(svgEl);
  const doc = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + xml;
  downloadBlob(new Blob([doc], { type: "image/svg+xml" }), filename);
}

// PNG: render via the canvas backend (so the music-glyph font rasterizes
// correctly) at 2x for crispness, composite onto white, and download.
export async function exportPng(musicXml: string, filename = "transcription.png") {
  const container = await renderHidden(musicXml, { backend: "canvas", zoom: 2 });
  try {
    const rendered = container.querySelector("canvas") as HTMLCanvasElement | null;
    if (!rendered) throw new Error("Canvas render produced no canvas element.");

    // Flatten onto a white background (the rendered canvas may be transparent).
    const out = document.createElement("canvas");
    out.width = rendered.width;
    out.height = rendered.height;
    const ctx = out.getContext("2d");
    if (!ctx) throw new Error("Could not get a 2D canvas context.");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(rendered, 0, 0);

    const blob: Blob = await new Promise((resolve, reject) =>
      out.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG encoding failed."))), "image/png")
    );
    downloadBlob(blob, filename);
  } finally {
    container.remove();
  }
}

// PDF: render at A4 portrait (multi-page) and place each page's SVG into the PDF
// as vector via svg2pdf.js. Matches the on-screen engraving (music symbols are
// SVG paths). Minor svg2pdf transparency quirks are acceptable.
export async function exportPdf(musicXml: string, filename = "transcription.pdf") {
  const [{ jsPDF }] = await Promise.all([import("jspdf"), import("svg2pdf.js")]);
  const container = await renderHidden(musicXml, { backend: "svg", pageFormat: "A4_P" });
  try {
    const svgs = Array.from(container.querySelectorAll("svg")) as SVGElement[];
    if (svgs.length === 0) throw new Error("PDF render produced no pages.");

    const pdf = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" });
    const w = pdf.internal.pageSize.getWidth();
    const h = pdf.internal.pageSize.getHeight();
    for (let i = 0; i < svgs.length; i++) {
      if (i > 0) pdf.addPage("a4", "portrait");
      await pdf.svg(svgs[i], { x: 0, y: 0, width: w, height: h });
    }
    pdf.save(filename);
  } finally {
    container.remove();
  }
}
