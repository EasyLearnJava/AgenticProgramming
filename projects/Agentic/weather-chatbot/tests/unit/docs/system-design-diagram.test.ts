/*
 * tests/unit/docs/system-design-diagram.test.ts: the System design diagram's layout: every part inside its band and the
 * drawing, no two parts on top of each other, each line short enough for its box, and the reference's numbers.
 */
import { describe, expect, it } from "vitest";
import { SYSTEM_DIAGRAM } from "@/lib/docs/system-design-diagram";

// About how wide a character is, in the drawing's units: the box text (14, plain) and a box's title (17, bold).
const LINE_CHAR_WIDTH = 7.4;
const TITLE_CHAR_WIDTH = 10;
// Where the text sits in a box, as the diagram's component draws it; a badge takes room beside the title.
const BOX_PADDING = 14;
const FIRST_LINE_Y = 52;
const LINE_HEIGHT = 20;
const ROOM_BELOW = 8;
const BADGE_ROOM = 40;

describe("the system design diagram", () => {
  it("draws every part inside the drawing, and inside its own band", () => {
    for (const box of SYSTEM_DIAGRAM.boxes) {
      const band = SYSTEM_DIAGRAM.bands.find((each) => each.letter === box.band);
      if (band === undefined) {
        throw new Error(`${box.title} names no band`);
      }
      expect(box.x, box.title).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, box.title).toBeLessThanOrEqual(SYSTEM_DIAGRAM.width);
      expect(box.y, box.title).toBeGreaterThanOrEqual(band.y);
      expect(box.y + box.height, box.title).toBeLessThanOrEqual(band.y + band.height);
    }
  });

  it("puts no part on top of another", () => {
    const boxes = SYSTEM_DIAGRAM.boxes;
    for (const [index, a] of boxes.entries()) {
      for (const b of boxes.slice(index + 1)) {
        const isApart = a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y;
        expect(isApart, `${a.title} and ${b.title}`).toBe(true);
      }
    }
  });

  it("keeps each line short enough for its box, and each box tall enough for its lines", () => {
    for (const box of SYSTEM_DIAGRAM.boxes) {
      const room = box.width - BOX_PADDING - BOX_PADDING;
      const titleRoom = box.badge === undefined ? room : room - BADGE_ROOM;
      expect(box.title.length * TITLE_CHAR_WIDTH, box.title).toBeLessThanOrEqual(titleRoom);
      for (const line of box.lines) {
        expect(line.length * LINE_CHAR_WIDTH, line).toBeLessThanOrEqual(room);
      }
      const lastLineY = FIRST_LINE_Y + (box.lines.length - 1) * LINE_HEIGHT;
      expect(lastLineY + ROOM_BELOW, box.title).toBeLessThanOrEqual(box.height);
    }
  });

  it("numbers the parts with the reference's numbers, and marks the one only Nimbus has with +", () => {
    const badges = SYSTEM_DIAGRAM.boxes.flatMap((box) => (box.badge === undefined ? [] : [box.badge]));
    expect(badges.sort()).toEqual(["+", "01", "02", "04", "06", "07"]);
  });
});
