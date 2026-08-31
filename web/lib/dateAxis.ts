// Gapless categorical daily x-axis helpers. Daily bars plotted on a Plotly
// DATE axis + weekend `rangebreaks` fragment line traces: the bar timestamps
// sit at 00:00 UTC, which a negative-offset browser (ET) renders on the prior
// evening, pushing points INTO the sat→mon break where Plotly clips them.
// Using date-STRING categories (formatted in UTC) sidesteps timezone shifts
// and needs no rangebreaks — every trading day is evenly spaced, lines connect.

// Session date as "YYYY-MM-DD", always in UTC (the bar's 00:00 UTC stamp).
export function isoDay(tSec: number): string {
  return new Date(tSec * 1000).toISOString().slice(0, 10);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// One tick at the first trading day of each month, labelled "Mon 'YY" (UTC),
// so a long daily axis stays readable instead of showing every category.
export function monthlyTicks(tsSec: number[]): { tickvals: string[]; ticktext: string[] } {
  const tickvals: string[] = [];
  const ticktext: string[] = [];
  let prevMonth = -1;
  for (const t of tsSec) {
    const d = new Date(t * 1000);
    const m = d.getUTCMonth();
    if (m !== prevMonth) {
      tickvals.push(isoDay(t));
      ticktext.push(`${MONTHS[m]} '${String(d.getUTCFullYear()).slice(2)}`);
      prevMonth = m;
    }
  }
  return { tickvals, ticktext };
}
