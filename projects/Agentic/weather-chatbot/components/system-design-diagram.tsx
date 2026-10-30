/*
 * components/system-design-diagram.tsx: the System design page's diagram, drawn as SVG from the data the page passes
 * in (lib/docs/system-design-diagram.ts): the bands, the lines between the parts, the parts, and the legend. It scales
 * to the page's width; screen readers get its title and description.
 */
import type { ReactNode } from "react";
import type { ArrowKind, DiagramBand, DiagramBox, SystemDiagram } from "@/lib/types";

type SystemDesignDiagramProps = { diagram: SystemDiagram };

const ARROW_KINDS: readonly ArrowKind[] = ["request", "mcp", "state"];
const OURS_BADGE = "+";
// Where things sit, in the drawing's units: a band's panel, letter and title; a box's text and badge; the legend.
const BAND_X = 10;
const BAND_RADIUS = 18;
const BAND_LETTER_X = 40;
const BAND_LETTER_Y = 32;
const BAND_LETTER_RADIUS = 16;
const BAND_TITLE_X = 66;
const BAND_TITLE_Y = 39;
const BOX_RADIUS = 12;
const BOX_PADDING = 14;
const BOX_TITLE_Y = 28;
const BOX_FIRST_LINE_Y = 52;
const BOX_LINE_HEIGHT = 20;
const BADGE_INSET = 22;
const BADGE_RADIUS = 14;
const LEGEND_X = 30;
const LEGEND_ITEM_WIDTH = 300;
const LEGEND_LINE_LENGTH = 40;
const LEGEND_TEXT_GAP = 12;
// Text sits this far below a point to look centred on it.
const TEXT_DROP = 5;

/** Draws a band: its panel, as wide as the drawing, its letter in a circle, and its title. */
function drawBand(band: DiagramBand, width: number): ReactNode {
  const letterY = band.y + BAND_LETTER_Y;
  return (
    <g key={band.letter}>
      <rect
        className="sd-band"
        x={BAND_X}
        y={band.y}
        width={width - BAND_X - BAND_X}
        height={band.height}
        rx={BAND_RADIUS}
      />
      <circle className="sd-band-letter" cx={BAND_LETTER_X} cy={letterY} r={BAND_LETTER_RADIUS} />
      <text className="sd-band-letter-text" x={BAND_LETTER_X} y={letterY + TEXT_DROP} textAnchor="middle">
        {band.letter}
      </text>
      <text className="sd-band-title" x={BAND_TITLE_X} y={band.y + BAND_TITLE_Y}>
        {band.title}
      </text>
    </g>
  );
}

/** Draws a part: its box, its name, its lines, and its badge in the top corner. */
function drawBox(box: DiagramBox): ReactNode {
  const isOurs = box.badge === OURS_BADGE;
  const textX = box.x + BOX_PADDING;
  const badgeX = box.x + box.width - BADGE_INSET;
  const badgeY = box.y + BADGE_INSET;
  return (
    <g key={box.title}>
      <rect
        className={isOurs ? "sd-box sd-box-ours" : "sd-box"}
        x={box.x}
        y={box.y}
        width={box.width}
        height={box.height}
        rx={BOX_RADIUS}
      />
      <text className="sd-box-title" x={textX} y={box.y + BOX_TITLE_Y}>
        {box.title}
      </text>
      {box.lines.map((line, index) => (
        <text key={line} className="sd-box-line" x={textX} y={box.y + BOX_FIRST_LINE_Y + index * BOX_LINE_HEIGHT}>
          {line}
        </text>
      ))}
      {box.badge === undefined ? null : (
        <g>
          <circle className={isOurs ? "sd-badge sd-badge-ours" : "sd-badge"} cx={badgeX} cy={badgeY} r={BADGE_RADIUS} />
          <text className="sd-badge-text" x={badgeX} y={badgeY + TEXT_DROP} textAnchor="middle">
            {box.badge}
          </text>
        </g>
      )}
    </g>
  );
}

/** Draws the legend: a sample of each kind of line, with what it means, and what the badges mean. */
function drawLegend(legend: SystemDiagram["legend"], width: number): ReactNode {
  const textY = legend.y + TEXT_DROP;
  return (
    <g>
      {legend.items.map((item, index) => {
        const x = LEGEND_X + index * LEGEND_ITEM_WIDTH;
        return (
          <g key={item.kind}>
            <path
              className={`sd-arrow sd-arrow-${item.kind}`}
              d={`M ${x} ${legend.y} h ${LEGEND_LINE_LENGTH}`}
              markerEnd={`url(#sd-head-${item.kind})`}
            />
            <text className="sd-legend" x={x + LEGEND_LINE_LENGTH + LEGEND_TEXT_GAP} y={textY}>
              {item.text}
            </text>
          </g>
        );
      })}
      <text className="sd-legend" x={width - LEGEND_X} y={textY} textAnchor="end">
        {legend.note}
      </text>
    </g>
  );
}

/** The diagram of how Nimbus is built: the bands, then the lines, the parts on top of them, and the legend. */
export function SystemDesignDiagram({ diagram }: SystemDesignDiagramProps): ReactNode {
  return (
    <figure className="sd-figure">
      <svg
        className="sd-svg"
        viewBox={`0 0 ${diagram.width} ${diagram.height}`}
        role="img"
        aria-labelledby="sd-title"
        aria-describedby="sd-desc"
      >
        <title id="sd-title">{diagram.title}</title>
        <desc id="sd-desc">{diagram.description}</desc>
        <defs>
          {ARROW_KINDS.map((kind) => (
            <marker
              key={kind}
              id={`sd-head-${kind}`}
              className={`sd-head-${kind}`}
              viewBox="0 0 10 10"
              refX="10"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" />
            </marker>
          ))}
        </defs>
        {diagram.bands.map((band) => drawBand(band, diagram.width))}
        {diagram.arrows.map((arrow) => (
          <path
            key={arrow.path}
            className={`sd-arrow sd-arrow-${arrow.kind}`}
            d={arrow.path}
            markerEnd={arrow.hasHead ? `url(#sd-head-${arrow.kind})` : undefined}
          />
        ))}
        {diagram.boxes.map(drawBox)}
        {diagram.labels.map((label) => (
          <text key={label.text} className="sd-label" x={label.x} y={label.y}>
            {label.text}
          </text>
        ))}
        {drawLegend(diagram.legend, diagram.width)}
      </svg>
      <figcaption>{diagram.title}. On a small screen, pinch to zoom; every part is also described below.</figcaption>
    </figure>
  );
}
