import {buildChart} from './chart.js';
import {beatPosition, timeAtBeat, snapTime, moveNote, resizeHold} from './editor-model.js';

const $ = id => document.getElementById(id);
const colors = ['#ad9bff','#68d6c4','#ad9bff','#68d6c4'];
const clock = value => `${Math.floor(Math.max(0,value)/60)}:${String(Math.floor(Math.max(0,value)%60)).padStart(2,'0')}`;

export function createMapEditor({getTracks, getSigns, onExit, onSave}) {
  const root=$('mapEditor'), canvas=$('editorCanvas'), ctx=canvas.getContext('2d');
  let songs=[], track=null, signs=[], notes=[], selected=null, tool='move', paletteSlot=0;
  let view=0, zoom=90, nextId=1, drag=null, history=[], future=[], busy=false, opened=false;
  let media=new Audio(), saved=false;
  const division=()=>Number($('editorSnap').value);
  const selectedNote=()=>notes.find(note=>note.id===selected);
  const status=text=>$('editorStatus').textContent=text;
  const snapshot=()=>JSON.stringify(notes);
  const checkpoint=()=>{history.push(snapshot());if(history.length>60)history.shift();future=[];};
  const draftKey=()=>`signs-map-draft-${track?.id}`;
  function draft(){
    if(!track)return;
    saved=false;
    try{localStorage.setItem(draftKey(),JSON.stringify({name:$('editorMapName').value,notes,signs}));}catch{}
  }
  function inspector(){
    const note=selectedNote();
    $('editorSelection').textContent=note?`${note.duration?'HOLD':'TAP'} / ${signs[note.signSlot]}`:'Select a bar to edit it.';
    for(const id of ['editorNoteSign','editorNoteLane','editorNoteTime','editorNoteDuration','editorDelete'])$(id).disabled=!note;
    if(note){$('editorNoteSign').value=note.signSlot;$('editorNoteLane').value=note.lane;$('editorNoteTime').value=note.time.toFixed(3);$('editorNoteDuration').value=note.duration.toFixed(3);}
    $('editorNoteCount').textContent=`${notes.length} notes`;
    $('editorSave').disabled=busy||!track||!notes.length;
    $('editorUndo').disabled=!history.length;$('editorRedo').disabled=!future.length;
  }
  function populatePalette(){
    $('editorPalette').replaceChildren();$('editorNoteSign').replaceChildren();
    signs.forEach((sign,slot)=>{
      const button=document.createElement('button');button.className='editor-sign';button.draggable=true;button.textContent=`${slot+1} ${sign}`;button.title=`Drag slot ${slot+1}: ${sign}`;
      button.classList.toggle('selected',paletteSlot===slot);button.onclick=()=>{paletteSlot=slot;populatePalette();};
      button.addEventListener('dragstart',event=>{event.dataTransfer.setData('text/plain',String(slot));event.dataTransfer.effectAllowed='copy';});
      $('editorPalette').append(button);const option=document.createElement('option');option.value=slot;option.textContent=`${slot+1} / ${sign}`;$('editorNoteSign').append(option);
    });inspector();
  }
  function generate(markDraft=true){
    if(!track)return;
    const base={...track};delete base.customMap;
    notes=buildChart(5,base,signs).map(note=>({id:nextId++,time:Math.max(0,note.time-(base.imported?3:0)),duration:note.duration,lane:note.lane,signSlot:signs.indexOf(note.sign)}));
    selected=null;if(markDraft)draft();inspector();status('Generated notes from song beats. Drag bars or tail handles to adjust.');
  }
  function loadTrack(id){
    if(track&&!saved)draft();media.pause();
    track=songs.find(song=>song.id===id);if(!track)return;
    signs=[...getSigns()];paletteSlot=0;view=0;selected=null;history=[];future=[];saved=false;
    $('editorMapName').value=track.customMap?.name||`${track.title} / My map`;
    notes=(track.customMap?.notes||[]).map(note=>({...note,id:nextId++}));
    if(!track.customMap)generate(false);
    saved=true;
    try{
      const stored=JSON.parse(localStorage.getItem(draftKey()));
      if(stored&&Array.isArray(stored.notes)&&stored.notes.every(n=>Number.isFinite(n.time)&&Number.isFinite(n.duration)&&n.time>=0&&n.duration>=0&&n.time+n.duration<=track.duration+.001&&Number.isInteger(n.lane)&&n.lane>=0&&n.lane<4&&Number.isInteger(n.signSlot)&&n.signSlot>=0&&n.signSlot<5)){
        notes=stored.notes.map(note=>({...note,id:nextId++}));$('editorMapName').value=stored.name;saved=false;
        status('Restored your local draft. Save map to use it in matches.');
      }
    }catch{}
    media=new Audio(track.audioUrl);media.preload='auto';media.volume=$('editorVolume').value/100;
    media.addEventListener('error',()=>status('Could not load this song for preview.'));
    media.addEventListener('ended',()=>{$('editorPreview').textContent='Play preview';});
    $('editorView').max=track.duration;$('editorView').value=0;$('editorBpm').textContent=`${track.bpm} BPM`;
    $('editorNoteTime').max=track.duration;$('editorNoteDuration').max=track.duration;
    populatePalette();inspector();
  }
  async function refreshSongs(preferred){
    songs=await getTracks();$('editorSong').replaceChildren();
    for(const song of songs){const option=document.createElement('option');option.value=song.id;option.textContent=`${song.title} / ${song.bpm} BPM`;$('editorSong').append(option);}
    const target=songs.find(song=>song.id===preferred)||songs[0];
    if(target){$('editorSong').value=target.id;loadTrack(target.id);}else{track=null;notes=[];inspector();status('Import an MP3 or add one to songs, then reopen the editor once analyzed.');}
  }
  async function open(preferred){
    opened=true;root.hidden=false;$('gameScreen').hidden=true;status('Loading songs...');
    try{await refreshSongs(preferred);}catch(error){status(error.message);}
  }
  function exit(){
    if(!saved)draft();media.pause();opened=false;root.hidden=true;$('gameScreen').hidden=false;onExit();
  }
  function coordinates(event){const r=canvas.getBoundingClientRect();return {x:event.clientX-r.left,y:event.clientY-r.top,width:r.width,height:r.height};}
  const yFor=(time,height)=>height-32-(time-view)*zoom;
  const timeFor=(y,height)=>view+(height-32-y)/zoom;
  const laneFor=(x,width)=>Math.max(0,Math.min(3,Math.floor((x-62)/((width-62)/4))));
  function hitNote(point){
    const laneWidth=(point.width-62)/4;
    for(const note of [...notes].reverse()){
      const x=62+(note.lane+.5)*laneWidth,y=yFor(note.time,point.height),end=yFor(note.time+note.duration,point.height);
      if(note.duration&&Math.abs(point.x-x)<15&&Math.abs(point.y-end)<12)return {note,kind:'tail'};
      if(Math.abs(point.x-x)<laneWidth*.4&&Math.abs(point.y-y)<16)return {note,kind:'head'};
      if(note.duration&&Math.abs(point.x-x)<10&&point.y>Math.min(y,end)&&point.y<Math.max(y,end))return {note,kind:'head'};
    }
    return null;
  }
  function addNote(point,slot=paletteSlot){
    if(!track||point.x<62)return;
    checkpoint();const time=snapTime(track,timeFor(point.y,point.height),division());
    const end=tool==='hold'?Math.min(track.duration,timeAtBeat(track,beatPosition(track,time)+1)):time;
    const note={id:nextId++,time,duration:Math.max(0,end-time),lane:laneFor(point.x,point.width),signSlot:slot};
    notes.push(note);selected=note.id;draft();inspector();return note;
  }
  function seek(time){
    if(!track)return;
    try{media.currentTime=Math.max(0,Math.min(track.duration,time));}catch{}
  }
  canvas.addEventListener('pointerdown',event=>{
    if(!track||event.button!==0)return;
    const point=coordinates(event);const hit=hitNote(point);
    if(hit){selected=hit.note.id;drag={kind:hit.kind,original:{...hit.note},start:timeFor(point.y,point.height),changed:false};inspector();canvas.setPointerCapture(event.pointerId);}
    else if(tool!=='move'){addNote(point);}
    else seek(timeFor(point.y,point.height));
  });
  canvas.addEventListener('pointermove',event=>{
    if(!drag||!track)return;
    const point=coordinates(event);if(!drag.changed){checkpoint();drag.changed=true;}
    const index=notes.findIndex(n=>n.id===drag.original.id);
    notes[index]=drag.kind==='tail'?resizeHold(track,drag.original,timeFor(point.y,point.height),division()):
      moveNote(track,drag.original,drag.original.time+timeFor(point.y,point.height)-drag.start,laneFor(point.x,point.width),division());
    inspector();
  });
  const finishDrag=()=>{if(drag?.changed){draft();status('Note snapped to '+(division()?`1/${division()} beat.`:'free timing.'));}drag=null;};
  for(const type of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(type,finishDrag);
  canvas.addEventListener('dblclick',event=>{if(tool==='move')addNote(coordinates(event));});
  canvas.addEventListener('contextmenu',event=>{event.preventDefault();const hit=hitNote(coordinates(event));if(hit){selected=hit.note.id;removeNote();}});
  canvas.addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect='copy';});
  canvas.addEventListener('drop',event=>{event.preventDefault();const slot=Number(event.dataTransfer.getData('text/plain'));if(Number.isInteger(slot)&&slot>=0&&slot<5)addNote(coordinates(event),slot);});
  canvas.addEventListener('wheel',event=>{
    if(!track)return;event.preventDefault();view=Math.max(0,Math.min(track.duration,view+event.deltaY/zoom*.5));$('editorFollow').checked=false;$('editorView').value=view;
  },{passive:false});
  function removeNote(){if(!selectedNote())return;checkpoint();notes=notes.filter(note=>note.id!==selected);selected=null;draft();inspector();}
  function setTool(value){tool=value;for(const name of ['move','tap','hold'])$('editor'+name[0].toUpperCase()+name.slice(1)).classList.toggle('selected',name===tool);}
  $('editorMove').onclick=()=>setTool('move');$('editorTap').onclick=()=>setTool('tap');$('editorHold').onclick=()=>setTool('hold');
  $('editorDelete').onclick=removeNote;
  $('editorGenerate').onclick=()=>{checkpoint();generate();};
  $('editorClear').onclick=()=>{checkpoint();notes=[];selected=null;draft();inspector();status('Empty map ready. Drop a sign onto a lane to add a note.');};
  $('editorUndo').onclick=()=>{if(!history.length)return;future.push(snapshot());notes=JSON.parse(history.pop());selected=null;draft();inspector();};
  $('editorRedo').onclick=()=>{if(!future.length)return;history.push(snapshot());notes=JSON.parse(future.pop());selected=null;draft();inspector();};
  $('editorMapName').oninput=draft;
  $('editorSong').onchange=()=>loadTrack($('editorSong').value);
  $('editorZoom').oninput=()=>{zoom=Number($('editorZoom').value);};
  $('editorView').oninput=()=>{view=Number($('editorView').value);$('editorFollow').checked=false;if(media.paused)seek(view);};
  $('editorVolume').oninput=()=>{media.volume=$('editorVolume').value/100;};
  $('editorPreview').onclick=async()=>{
    if(!track)return;
    if(!media.paused){media.pause();$('editorPreview').textContent='Play preview';return;}
    try{await media.play();$('editorPreview').textContent='Pause preview';}catch{status('Audio preview could not start. Try loading the song again.');}
  };
  $('editorStop').onclick=()=>{media.pause();seek(0);view=0;$('editorView').value=0;$('editorPreview').textContent='Play preview';};
  $('editorExit').onclick=exit;
  for(const [id,property] of [['editorNoteSign','signSlot'],['editorNoteLane','lane'],['editorNoteTime','time'],['editorNoteDuration','duration']]){
    $(id).onchange=()=>{
      const note=selectedNote();if(!note||!track)return;
      const value=Number($(id).value);if(!Number.isFinite(value))return;
      checkpoint();
      if(property==='time'){Object.assign(note,moveNote(track,note,value,note.lane,division()));}
      else if(property==='duration'){Object.assign(note,resizeHold(track,note,note.time+Math.max(0,value),division()));}
      else note[property]=Math.max(0,Math.min(property==='lane'?3:4,Math.round(value)));
      draft();inspector();
    };
  }
  $('editorSave').onclick=async()=>{
    if(!track||busy)return;busy=true;inspector();status('Saving map...');
    try{
      const response=await fetch('/api/maps/'+encodeURIComponent(track.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('editorMapName').value,signs,notes:notes.map(({time,duration,lane,signSlot})=>({time,duration,lane,signSlot}))})});
      const result=await response.json();if(!response.ok)throw new Error(result.error||'Could not save map.');
      track.customMap=result;saved=true;try{localStorage.removeItem(draftKey());}catch{}
      await onSave(track);status('Map saved. Select this song in the track list to play your map.');
    }catch(error){status(error.message);}finally{busy=false;inspector();}
  };
  $('editorImport').onclick=()=>{if(!busy)$('editorFile').click();};
  $('editorFile').onchange=async()=>{
    const file=$('editorFile').files[0];$('editorFile').value='';if(!file||busy)return;
    if(!file.name.toLowerCase().endsWith('.mp3')||file.size>100*1024*1024){status('Choose an MP3 under 100 MB.');return;}
    busy=true;inspector();$('editorImport').disabled=true;
    try{
      const response=await fetch('/api/tracks/import',{method:'POST',headers:{'Content-Type':'audio/mpeg','X-Filename':encodeURIComponent(file.name)},body:file});
      const uploaded=await response.json();if(!response.ok)throw new Error(uploaded.error||'Upload failed.');
      const track=await new Promise((resolve,reject)=>{
        const check=async()=>{try{const response=await fetch('/api/imports/'+uploaded.id);if(!response.ok)throw new Error('Analysis status unavailable.');const job=await response.json();status(job.message);if(job.status==='complete')resolve(job.track);else if(job.status==='error')reject(new Error(job.message));else setTimeout(check,1000);}catch(error){reject(error);}};check();
      });
      if(opened)await refreshSongs(track.id);
    }catch(error){status(error.message);}finally{busy=false;$('editorImport').disabled=false;inspector();}
  };
  document.addEventListener('keydown',event=>{
    if(!opened||event.target.closest('dialog')||['INPUT','SELECT','TEXTAREA'].includes(event.target.tagName))return;
    if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();removeNote();}
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'){event.preventDefault();(event.shiftKey?$('editorRedo'):$('editorUndo')).click();}
    if(event.key===' '&&event.target.tagName!=='BUTTON'){event.preventDefault();$('editorPreview').click();}
  });
  function draw(){
    requestAnimationFrame(draw);if(!opened)return;
    const r=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1;
    if(canvas.width!==Math.round(r.width*ratio)||canvas.height!==Math.round(r.height*ratio)){canvas.width=Math.round(r.width*ratio);canvas.height=Math.round(r.height*ratio);}
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,r.width,r.height);const laneWidth=(r.width-62)/4;
    if(!track)return;
    const windowLength=(r.height-64)/zoom,playhead=media.currentTime||0;
    if(!media.paused&&$('editorFollow').checked&&(playhead<view||playhead>view+windowLength*.8)){view=Math.max(0,playhead-windowLength*.2);$('editorView').value=view;}
    const first=Math.floor(beatPosition(track,view)*(division()||1)),last=Math.ceil(beatPosition(track,Math.min(track.duration,view+windowLength+1))*(division()||1));
    for(let grid=first;grid<=Math.min(last,first+4000);grid++){
      const beat=grid/(division()||1),time=timeAtBeat(track,beat),y=yFor(time,r.height);if(y<0||y>r.height||time<0||time>track.duration)continue;
      const major=Math.abs(beat-Math.round(beat))<1e-7;ctx.strokeStyle=major?'#494051':'#211c28';ctx.lineWidth=major?1:.5;
      ctx.beginPath();ctx.moveTo(62,y);ctx.lineTo(r.width,y);ctx.stroke();
      if(major){ctx.fillStyle='#929db6';ctx.font='9px Courier New';ctx.textAlign='right';ctx.fillText(time.toFixed(2),54,y+3);}
    }
    for(let lane=0;lane<5;lane++){ctx.strokeStyle='#302637';ctx.beginPath();ctx.moveTo(62+lane*laneWidth,0);ctx.lineTo(62+lane*laneWidth,r.height);ctx.stroke();}
    for(const note of notes){
      const x=62+(note.lane+.5)*laneWidth,y=yFor(note.time,r.height),end=yFor(note.time+note.duration,r.height);if(y<-20||end>r.height+20)continue;
      ctx.strokeStyle=colors[note.lane];ctx.fillStyle=colors[note.lane];
      if(note.duration){ctx.lineWidth=note.id===selected?6:3;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x,end);ctx.stroke();ctx.fillRect(x-6,end-5,12,10);}
      ctx.fillStyle=note.id===selected?colors[note.lane]+'66':'#16111e';ctx.lineWidth=note.id===selected?2:1;
      ctx.beginPath();ctx.roundRect(x-laneWidth*.38,y-13,laneWidth*.76,26,3);ctx.fill();ctx.stroke();
      ctx.fillStyle=colors[note.lane];ctx.font=`${laneWidth<90?8:10}px Courier New`;ctx.textAlign='center';ctx.fillText(signs[note.signSlot].toUpperCase(),x,y+3);
    }
    const cursor=yFor(playhead,r.height);ctx.strokeStyle='#eff0ff';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(62,cursor);ctx.lineTo(r.width,cursor);ctx.stroke();
    $('editorAudioTime').textContent=`${clock(playhead)} / ${clock(track.duration)}`;
    $('editorViewLabel').textContent=`${clock(view)} - ${clock(Math.min(track.duration,view+windowLength))}`;
  }
  requestAnimationFrame(draw);
  return {open,exit,isOpen:()=>opened};
}
