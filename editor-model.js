export function beatPosition(track, time) {
  const beats = track.beats || [];
  const period = 60 / track.bpm;
  if (!beats.length) return time / period;
  if (time <= beats[0]) return (time - beats[0]) / (beats[1] - beats[0] || period);
  let low = 0, high = beats.length - 1;
  while (low + 1 < high) {const middle = (low + high) >> 1; if (beats[middle] <= time) low = middle; else high = middle;}
  if (time >= beats.at(-1)) return beats.length - 1 + (time - beats.at(-1)) / (beats.at(-1) - beats.at(-2) || period);
  return low + (time - beats[low]) / (beats[low + 1] - beats[low]);
}

export function timeAtBeat(track, position) {
  const beats = track.beats || [], period = 60 / track.bpm;
  if (!beats.length) return position * period;
  if (position <= 0) return beats[0] + position * (beats[1] - beats[0] || period);
  if (position >= beats.length - 1) return beats.at(-1) + (position - beats.length + 1) * (beats.at(-1) - beats.at(-2) || period);
  const index = Math.floor(position);
  return beats[index] + (position - index) * (beats[index + 1] - beats[index]);
}

export function snapTime(track, time, division) {
  if (!division) return Math.max(0, Math.min(track.duration, time));
  const position = Math.round(beatPosition(track, time) * division) / division;
  return Math.max(0, Math.min(track.duration, timeAtBeat(track, position)));
}

export function moveNote(track, note, time, lane, division) {
  const start = Math.min(snapTime(track, time, division), Math.max(0, track.duration - note.duration));
  return {...note, time: start, lane: Math.max(0, Math.min(3, lane))};
}

export function resizeHold(track, note, endTime, division) {
  const end = snapTime(track, endTime, division);
  return {...note, duration: Math.max(0, end - note.time)};
}
