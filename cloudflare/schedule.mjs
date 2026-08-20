export const JOB_NAMES = Object.freeze([
  "input-prefetch",
  "daily-radar",
  "pre-earnings",
  "post-bmo",
  "post-digest-bmo",
  "post-amc",
  "post-digest-amc",
  "weekly-radar",
  "transcript-cache",
]);

const WEEKDAYS = new Set(["Mon", "Tue", "Wed", "Thu", "Fri"]);
const TRANSCRIPT_DAYS = new Set(["Tue", "Thu", "Sat"]);

export function easternScheduleParts(scheduledTime) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(scheduledTime));
  return Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
}

export function jobsForEasternSlot(scheduledTime) {
  const { weekday, hour, minute } = easternScheduleParts(scheduledTime);
  const slot = `${hour}:${minute}`;
  const jobs = [];

  if (WEEKDAYS.has(weekday) && slot === "08:00") jobs.push("input-prefetch");
  if (WEEKDAYS.has(weekday) && slot === "09:30") jobs.push("daily-radar", "post-bmo");
  if (WEEKDAYS.has(weekday) && slot === "10:00") jobs.push("post-digest-bmo");
  if (WEEKDAYS.has(weekday) && slot === "17:00") jobs.push("pre-earnings");
  if (WEEKDAYS.has(weekday) && slot === "18:00") jobs.push("post-amc");
  if (WEEKDAYS.has(weekday) && slot === "19:30") jobs.push("post-digest-amc");
  if (weekday === "Sun" && slot === "17:00") jobs.push("weekly-radar");
  if (TRANSCRIPT_DAYS.has(weekday) && slot === "02:30") jobs.push("transcript-cache");

  return jobs;
}

export function scheduledRunId(jobName, scheduledTime) {
  return `scheduled-${jobName}-${new Date(scheduledTime).toISOString().replaceAll(":", "-")}`;
}

