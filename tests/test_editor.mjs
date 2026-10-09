import assert from 'node:assert/strict';
import {beatPosition,timeAtBeat,snapTime,moveNote,resizeHold} from '../editor-model.js';
import {buildChart} from '../chart.js';
const track={bpm:120,duration:10,beats:[.2,.7,1.2,1.8,2.3,2.8,3.3,3.8,4.3,4.8,5.3,5.8,6.3,6.8,7.3,7.8,8.3,8.8,9.3,9.8]};
for(const subdivision of [4,8,16]){
  for(const time of [.4,1.5,2.15,3.12,7.61]){
    const snapped=snapTime(track,time,subdivision);
    const beat=beatPosition(track,snapped)*subdivision;
    assert.ok(Math.abs(beat-Math.round(beat))<1e-8);
    assert.ok(Math.abs(timeAtBeat(track,beatPosition(track,time))-time)<1e-8);
  }
}
assert.equal(snapTime(track,1.523,0),1.523);
const moved=moveNote(track,{time:1,duration:2,lane:0},9,3,4);
assert.equal(moved.lane,3);assert.ok(moved.time+moved.duration<=10);
assert.equal(resizeHold(track,{time:2,duration:1},1,4).duration,0);
const map={...track,imported:true,customMap:{notes:[{time:1,duration:.75,lane:2,signSlot:4}]}};
const chart=buildChart(3,map,['dog','boar','ox','bird','ram']);
assert.deepEqual({time:chart[0].time,duration:chart[0].duration,lane:chart[0].lane,sign:chart[0].sign},{time:4,duration:.75,lane:2,sign:'boar'});
console.log('PASS: subdivision snapping, variable beats, movement, hold resizing, custom-map playback');
