import assert from 'node:assert/strict';
import {buildChart, signOrder} from '../chart.js';
import {tracks} from '../tracks.js';

const beats = Array.from({length: 120}, (_, i) => .25 + i * .48 + Math.sin(i * .2) * .03);
for (let count = 3; count <= 5; count++) {
  const imported = {imported: true, beats, bpm: 125, seed: 3};
  for (const track of [...tracks, imported]) {
    const chart = buildChart(count, track);
    assert.deepEqual([...new Set(chart.map(n => n.sign))].sort(), signOrder.slice(0, count).sort());
    chart.forEach((note, i) => {
      assert.ok(note.lane >= 0 && note.lane <= 3);
      if (track.imported) {
        assert.ok(beats.some(t => Math.abs(note.time - 3 - t) < 1e-8));
        if (note.duration) assert.ok(beats.some(t => Math.abs(note.time + note.duration - 3 - t) < 1e-8));
        if (i + 1 < chart.length) {
          const endIndex = beats.findIndex(t => Math.abs(note.time + note.duration - 3 - t) < 1e-8);
          assert.ok(Math.abs(chart[i + 1].time - 3 - beats[endIndex + 1]) < 1e-8);
        }
      } else {
        const beat = 60 / track.bpm;
        assert.ok(Math.abs(note.time / beat - Math.round(note.time / beat)) < 1e-8);
        assert.ok(note.time + note.duration < 60);
        if (i + 1 < chart.length) assert.ok(Math.abs(chart[i + 1].time - note.time - note.duration - beat) < 1e-8);
      }
    });
  }
}
console.log('PASS: built-in and imported beatmaps at all 3 difficulties');

const custom = ['boar','dog','ox','ram','bird'];
for (const count of [3,4,5,12]) {
  const chart = buildChart(count, tracks[0], custom);
  assert.deepEqual([...new Set(chart.map(n=>n.sign))].sort(),custom.slice(0,Math.min(5,count)).sort());
}
console.log('PASS: custom sign selections and maximum-five cap');

const importedChart = buildChart(5, {imported:true,beats,bpm:125,seed:0});
for (const beat of beats) {
  assert.ok(importedChart.some(note => beat + 3 >= note.time - 1e-8 && beat + 3 <= note.time + note.duration + 1e-8));
}
console.log('PASS: every song beat is covered by a sign or hold');
