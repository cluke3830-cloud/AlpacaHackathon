export type Bar = { t: number; o: number; h: number; l: number; c: number; v: number };

// Standard Heikin Ashi: haC=(o+h+l+c)/4; haO=(prevHaO+prevHaC)/2 (seed (o+c)/2);
// haH/haL envelope the raw extreme and the HA body.
export function toHeikinAshi(bars: Bar[]): Bar[] {
  const out: Bar[] = [];
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const haC = (b.o + b.h + b.l + b.c) / 4;
    const haO = i === 0 ? (b.o + b.c) / 2 : (out[i - 1].o + out[i - 1].c) / 2;
    out.push({
      t: b.t,
      o: haO,
      h: Math.max(b.h, haO, haC),
      l: Math.min(b.l, haO, haC),
      c: haC,
      v: b.v,
    });
  }
  return out;
}
