import { createMapEditor } from './editor.js';
import { tracks } from './tracks.js';
import { signOrder, buildChart, holdResult, selectedSignPool } from './chart.js';
const $ = id => document.getElementById(id);
const data = await fetch('/assets/hand_signs.json', {cache:'no-store'}).then(r => r.json());
const reference = await fetch('/assets/sign_reference.json').then(r => r.json());
const signs = Object.keys(data.signs), colors = ['#ad9bff','#68d6c4','#ad9bff','#68d6c4'];
const connections = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
const keys = ['d','f','j','k'];
const pressedKeys = new Set(), pressedPointers = new Map();
let trackedSign='', trackedAt=0;
let mode = 'keys', phase = 'home', elapsed = 0, lastFrame = performance.now(), notes = [], score = 0, combo = 0, best = 0, perfect = 0, misses = 0, judged = 0, earned = 0;
let songAudio=null, songStarted=false, playClock=0, playOffset=0, countdownBeat=0;
let importedTracks=[], trackPage=0, trackChoices=[], importing=false;
let audio, master, beatIndex = 0, voices = [], flash = [0,0,0,0], feedbackUntil = 0;
let candidate = '', candidateAt = 0, latched = '', cameraOn = false, pollBusy = false;
const canvas = $('game'), ctx = canvas.getContext('2d');
let difficulty = 3, runDifficulty = 3;
let chosenSigns = signOrder.slice(0,5), activeSignSlot = 0, runSigns = chosenSigns.slice(0,3);
try{const saved=JSON.parse(localStorage.getItem('signs-selection'));if(Array.isArray(saved)&&saved.length===5&&new Set(saved).size===5&&saved.every(s=>signOrder.includes(s)))chosenSigns=saved;}catch{}

let selectedTrack = tracks[0], runTrack = tracks[0];
const beatLength = ()=>60/runTrack.bpm;
const countInLength = ()=>5*beatLength();
const runDuration = ()=>(runTrack.imported?runTrack.duration:60)+countInLength();
const formatTime = seconds=>`${Math.floor(Math.max(0,seconds)/60)}:${String(Math.floor(Math.max(0,seconds)%60)).padStart(2,'0')}`;
const setupPhase = ()=>['home','tracks','menu'].includes(phase);
let trackerConfigQueue = Promise.resolve(), starting = false;
function syncTrackerSigns(count, chosen=chosenSigns){
  const selected = selectedSignPool(count,chosen);
  trackerConfigQueue = trackerConfigQueue.catch(()=>{}).then(async()=>{
    const response = await fetch('/api/tracker/signs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({signs:selected})});
    if(!response.ok)throw new Error('Could not update tracker signs. Restart the game server.');
    candidate='';latched='';
  });
  return trackerConfigQueue;
}
function updateDifficulty(){
  difficulty = Math.max(3,Math.min(5,Number($('difficultySlider').value)));
  $('difficultyValue').textContent = `${difficulty} signs`;
  $('difficultySigns').textContent = selectedSignPool(difficulty,chosenSigns).join(' / ');
  $('difficultyHint').textContent = phase === 'paused' || phase === 'finished' ? 'Applies when you restart or play again.' : 'One more sign with each step.';
}
$('difficultySlider').oninput = ()=>{updateDifficulty();if(setupPhase())syncTrackerSigns(difficulty).catch(error=>{$('cameraStatus').textContent=error.message;});};
updateDifficulty();
syncTrackerSigns(difficulty).catch(error=>{$('cameraStatus').textContent=error.message;});
function poseDrawing(canvas, hands, color = '#ad9bff', fit = true) {
  const c = canvas.getContext('2d'); c.clearRect(0,0,canvas.width,canvas.height);
  if (!hands.length) return;
  const all = hands.flatMap(h => h.landmarks);
  const minX = Math.min(...all.map(p=>p[0])), maxX = Math.max(...all.map(p=>p[0]));
  const minY = Math.min(...all.map(p=>p[1])), maxY = Math.max(...all.map(p=>p[1]));
  const scale = Math.min((canvas.width-28)/Math.max(.01,maxX-minX),(canvas.height-20)/Math.max(.01,maxY-minY));
  const point = p => fit ? [(p[0]-(minX+maxX)/2)*scale+canvas.width/2,(p[1]-(minY+maxY)/2)*scale+canvas.height/2] : [p[0]*canvas.width,p[1]*canvas.height];
  hands.forEach((h,index)=>{
    c.strokeStyle = index ? '#68d6c4' : color; c.lineWidth = 1.5;
    for (const [a,b] of connections) {c.beginPath();c.moveTo(...point(h.landmarks[a]));c.lineTo(...point(h.landmarks[b]));c.stroke();}
    c.fillStyle = index ? '#a2eadf' : '#d5cbff';
    for(const p of h.landmarks){c.beginPath();c.arc(...point(p),2,0,Math.PI*2);c.fill();}
  });
}
function refreshLibrary(){
$('signGrid').replaceChildren();
for(const sign of signs){
  const card = document.createElement('div');card.className='sign-card';
  card.innerHTML=`<canvas width="220" height="150"></canvas><h3>${sign}</h3><small>${data.signs[sign].length} recorded samples · 2 hands</small>`;
  $('signGrid').append(card);poseDrawing(card.querySelector('canvas'),data.signs[sign][0]?.hands || []);
}
}
refreshLibrary();
function audioInit(){audio ||= new AudioContext();master ||= audio.createGain();master.gain.value=$('volume').value/100*.3;master.connect(audio.destination);audio.resume();}
function sound(time,frequency,duration,kind='sine',gain=.5){
  if(!audio)return;
  const osc=audio.createOscillator(),amp=audio.createGain();osc.type=kind;osc.frequency.setValueAtTime(frequency,time);
  if(kind==='sine')osc.frequency.exponentialRampToValueAtTime(Math.max(35,frequency*.45),time+duration);
  amp.gain.setValueAtTime(gain,time);amp.gain.exponentialRampToValueAtTime(.001,time+duration);
  osc.connect(amp);amp.connect(master);osc.start(time);osc.stop(time+duration);voices.push(osc);osc.onended=()=>{voices=voices.filter(v=>v!==osc);osc.disconnect();amp.disconnect();};
}
function stopAudio(){if(songAudio)songAudio.pause();for(const voice of [...voices]){try{voice.stop();}catch{}}voices=[];}
function scheduleBeat(){
  if(runTrack.imported)return;
  const musicTime=elapsed-countInLength();
  if(musicTime<0)return;
  while(beatIndex*beatLength()<=musicTime+.09){
    const b=beatIndex++, t=audio.currentTime+Math.max(0,b*beatLength()-musicTime);
    sound(t,b%2===0?runTrack.accent:runTrack.accent*1.6,b%2===0?.16:.07,'sine',.6);
    sound(t,6000,.025,'triangle',.08);
    if(b%2===0)sound(t,runTrack.chords[Math.floor(b/8)%4],beatLength()*.5,runTrack.wave,.12);
    if((b+runTrack.seed)%3===0)sound(t,runTrack.melody[(b+runTrack.seed)%4],beatLength()*.35,'sine',.07);
  }
}
function statistics(){
  $('score').textContent=String(score).padStart(6,'0');$('combo').textContent=`×${1+Math.floor(combo/10)}`;
  $('best').textContent=best;$('perfect').textContent=perfect;$('misses').textContent=misses;
  $('accuracy').textContent=(judged?earned/judged*100:100).toFixed(1);
}
function feedback(text,color){$('judgement').textContent=text;$('judgement').style.color=color;feedbackUntil=performance.now()+650;}
function completeNote(note){
  note.done=true;combo++;best=Math.max(best,combo);judged++;
  earned+=note.excellent?1:.7;perfect+=note.excellent?1:0;
  score+=(note.excellent?1000:700)*(1+Math.floor(combo/10))+(note.duration?(note.holdBeats||Math.round(note.duration/beatLength()))*500:0);
  feedback(note.duration?'HOLD COMPLETE':note.excellent?'PERFECT':'GOOD',colors[note.lane]);statistics();
}
function missNote(note){note.done=true;misses++;judged++;combo=0;feedback(note.started?'HOLD BROKEN':'MISS','#929db6');statistics();}
function hit(lane,sign=null,source='keyboard'){
  if(phase!=='playing')return;
  flash[lane]=performance.now()+180;
  const note=notes.filter(n=>!n.done&&!n.started&&n.lane===lane&&(!sign||n.sign===sign)).sort((a,b)=>Math.abs(a.time-elapsed)-Math.abs(b.time-elapsed))[0];
  if(!note||Math.abs(note.time-elapsed)>.23)return;
  note.excellent=Math.abs(note.time-elapsed)<=.1;
  if(note.duration){note.started=true;note.source=source;note.lastHeld=elapsed;feedback('HOLD',colors[lane]);}
  else completeNote(note);
}
function updateHolds(now){
  for(const note of notes){
    if(note.done)continue;
    if(!note.started){if(elapsed>note.time+.23)missNote(note);continue;}
    const matching=note.source==='hands'?trackedSign===note.sign&&now-trackedAt<250:
      note.source==='pointer'?[...pressedPointers.values()].includes(note.lane):pressedKeys.has(keys[note.lane]);
    const result=holdResult(note,elapsed,matching,note.source==='hands'?.18:0);
    if(result==='complete')completeNote(note);else if(result==='broken')missNote(note);
    else flash[note.lane]=now+80;
  }
}
function overlay(title,text,button,tag='SIGNS'){
  $('overlayTitle').textContent=title;$('overlayText').textContent=text;$('play').firstChild.textContent=button+' ';$('overlayTag').textContent=tag;$('overlay').style.display='flex';
  $('trackLibrary').hidden=phase!=='tracks';$('trackList').hidden=phase!=='tracks';$('difficultyControl').hidden=!['menu','paused','finished'].includes(phase);
  $('menuBack').hidden=!['tracks','menu','finished','loading'].includes(phase);
  $('menuBack').textContent=phase==='tracks'?'Back to start':'Back to tracks';
  $('shortcuts').hidden=['home','tracks'].includes(phase);updateDifficulty();
}
async function loadSong(track){
  if(songAudio){songAudio.pause();songAudio.removeAttribute('src');songAudio.load();songAudio=null;}
  if(!track.imported)return;
  songAudio=new Audio();songAudio.preload='auto';songAudio.volume=$('volume').value/100;
  const media=songAudio;
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>finish(new Error('Song loading timed out. Try again.')),20000);
    const finish=error=>{clearTimeout(timer);media.removeEventListener('canplay',ready);media.removeEventListener('error',failed);error?reject(error):resolve();};
    const ready=()=>finish();const failed=()=>finish(new Error('The browser could not play this MP3.'));
    media.addEventListener('canplay',ready,{once:true});media.addEventListener('error',failed,{once:true});media.src=track.audioUrl;media.load();
  });
}
function resetPlayClock(){playOffset=elapsed;playClock=audio.currentTime;}
async function start(){
  if(starting)return;starting=true;audioInit();stopAudio();
  const selectedDifficulty=difficulty, chosenTrack=selectedTrack, selectedSigns=[...chosenSigns];
  phase='loading';overlay('Loading track.','Preparing song and beatmap...','Loading','SIGNS');
  try{
    $('play').disabled=true;$('overlayText').textContent='Preparing track...';
    await syncTrackerSigns(selectedDifficulty,selectedSigns);await loadSong(chosenTrack);
    if(phase!=='loading'||selectedTrack!==chosenTrack){starting=false;$('play').disabled=false;stopAudio();return;}
  }catch(error){if(phase==='loading'){phase='menu';overlay(chosenTrack.title,error.message,'Try again','AUDIO LOAD ERROR');}starting=false;$('play').disabled=false;return;}
  starting=false;$('play').disabled=false;runDifficulty=selectedDifficulty;runTrack=chosenTrack;
  runSigns=selectedSignPool(runDifficulty,selectedSigns);notes=buildChart(runDifficulty,runTrack,selectedSigns).map(note=>({...note,time:note.time+countInLength()-(runTrack.imported?3:0)}));$('runDifficulty').textContent=`${runDifficulty} SIGNS`;
  pressedKeys.clear();pressedPointers.clear();elapsed=0;beatIndex=0;countdownBeat=0;songStarted=false;
  score=combo=best=perfect=misses=judged=earned=0;latched='';candidate='';phase='playing';
  resetPlayClock();$('overlay').style.display='none';statistics();
}
function playSong(){
  if(!songAudio)return;
  songAudio.play().catch(error=>{if(phase==='playing'){pause();$('overlayText').textContent='Audio playback stopped. Press Resume to try again.';}});
}
function pause(){
  if(phase==='playing'){phase='paused';stopAudio();overlay('PAUSED','Take a breath. The beat will wait.','Resume','ESC RESUME / R RESTART / Q MENU');}
  else if(phase==='paused'){audioInit();beatIndex=Math.max(0,Math.ceil((elapsed-countInLength())/beatLength()));resetPlayClock();phase='playing';if(runTrack.imported&&songStarted)playSong();$('overlay').style.display='none';}
}
function updateTrackInfo(){
  $('trackTitle').textContent=selectedTrack.title;$('trackBpm').textContent=`${selectedTrack.bpm} BPM`;
  $('trackArtist').textContent=(selectedTrack.imported?'Your music / ':'Signs Originals / ')+selectedTrack.mood;
  $('trackDuration').textContent=formatTime(selectedTrack.duration||60);
}
function menu(){phase='home';stopAudio();elapsed=0;notes=[];overlay('Find your flow.','Move your hands. Follow the music.','Start','SIGNS');}
function chooseTrack(track){selectedTrack=track;updateTrackInfo();phase='menu';overlay(track.title,`${track.bpm} BPM / ${track.mood} / ${formatTime(track.duration||60)}`,'Play track','CHOOSE YOUR DIFFICULTY');syncTrackerSigns(difficulty).catch(error=>{$('cameraStatus').textContent=error.message;});}
function renderTrackPage(){
  $('trackList').replaceChildren();
  const pages=Math.max(1,Math.ceil(trackChoices.length/5));trackPage=Math.max(0,Math.min(trackPage,pages-1));
  trackChoices.slice(trackPage*5,trackPage*5+5).forEach((track,i)=>{
    const button=document.createElement('button');button.className='track-option';
    const number=document.createElement('span');number.className='track-index';number.textContent=String(trackPage*5+i+1).padStart(2,'0');
    const details=document.createElement('span');details.className='track-details';
    const title=document.createElement('strong');title.textContent=track.title;
    const description=document.createElement('small');description.textContent=`${track.customMap?'CUSTOM MAP / ':track.imported?'MP3 / ':''}${formatTime(track.duration||60)} / ${track.mood}`;
    details.append(title,description);
    const tempo=document.createElement('span');tempo.className='track-tempo';tempo.textContent=Math.round(track.bpm);
    const unit=document.createElement('small');unit.textContent='BPM';tempo.append(unit);
    button.append(number,details,tempo);button.onclick=()=>chooseTrack(track);$('trackList').append(button);
  });
  $('trackPage').textContent=`${trackPage+1} / ${pages}`;$('previousTrackPage').disabled=trackPage===0;$('nextTrackPage').disabled=trackPage===pages-1;
}
function mergeTracks(builtins,loaded){
  const ids=new Set(builtins.map(t=>t.id));return [...loaded.filter(t=>!ids.has(t.id)),...builtins.map(t=>loaded.find(row=>row.id===t.id)||t)];
}
async function refreshImportedTracks(){
  const response=await fetch('/api/tracks',{cache:'no-store'});
  if(!response.ok)throw new Error('Restart the server to enable MP3 import.');
  importedTracks=await response.json();
}
function showTracks(){
  phase='tracks';stopAudio();elapsed=0;notes=[];trackPage=0;
  const shuffled=[...tracks];for(let i=shuffled.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[shuffled[i],shuffled[j]]=[shuffled[j],shuffled[i]];}
  trackChoices=mergeTracks(shuffled,importedTracks);renderTrackPage();
  overlay('Pick your track.','Choose an original beat or import your own MP3.','Surprise me','TRACK SELECT');
  refreshImportedTracks().then(()=>{if(phase==='tracks'){trackChoices=mergeTracks(shuffled,importedTracks);renderTrackPage();}}).catch(error=>{$('importStatus').textContent=error.message;});
}
$('previousTrackPage').onclick=()=>{trackPage--;renderTrackPage();};$('nextTrackPage').onclick=()=>{trackPage++;renderTrackPage();};
$('importTrack').onclick=()=>{if(!importing)$('mp3File').click();};
$('mp3File').onchange=async()=>{
  const file=$('mp3File').files[0];if(!file||importing)return;$('mp3File').value='';
  if(!file.name.toLowerCase().endsWith('.mp3')){$('importStatus').textContent='Choose an MP3 file.';return;}
  if(file.size>100*1024*1024){$('importStatus').textContent='Choose a file under 100 MB.';return;}
  importing=true;$('importTrack').disabled=true;$('importStatus').textContent='Uploading '+file.name+'...';
  try{
    const response=await fetch('/api/tracks/import',{method:'POST',headers:{'Content-Type':'audio/mpeg','X-Filename':encodeURIComponent(file.name)},body:file});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'Import failed.');
    await new Promise((resolve,reject)=>{
      const check=async()=>{
        try{
          const response=await fetch('/api/imports/'+result.id,{cache:'no-store'});if(!response.ok)throw new Error('Import status unavailable.');
          const job=await response.json();$('importStatus').textContent=job.message;
          if(job.status==='error')reject(new Error(job.message));
          else if(job.status==='complete')resolve(job.track);else setTimeout(check,1000);
        }catch(error){reject(error);}
      };check();
    });
    await refreshImportedTracks();$('importStatus').textContent='Beatmap saved. Select your song to play.';
    if(phase==='tracks'){trackChoices=mergeTracks(tracks,importedTracks);trackPage=0;renderTrackPage();}
  }catch(error){$('importStatus').textContent=error.message;}
  finally{importing=false;$('importTrack').disabled=false;}
};
function primaryAction(){if(phase==='home')showTracks();else if(phase==='tracks')chooseTrack(trackChoices[Math.floor(Math.random()*trackChoices.length)]);else if(phase==='paused')pause();else start();}
$('play').onclick=primaryAction;$('restart').onclick=()=>{if(['playing','paused','finished'].includes(phase))start();};$('menu').onclick=menu;
$('menuBack').onclick=()=>phase==='tracks'?menu():showTracks();
$('practice').onclick=()=>{if(phase==='playing')pause();$('library').showModal();};$('closeLibrary').onclick=()=>$('library').close();
$('volume').oninput=()=>{if(master)master.gain.value=$('volume').value/100*.3;if(songAudio)songAudio.volume=$('volume').value/100;};
function inputMode(next){mode=next;$('keys').classList.toggle('selected',mode==='keys');$('camera').classList.toggle('selected',mode==='hands');$('inputHint').innerHTML=mode==='keys'?'D · F · J · K<br>Press on the beat; hold keys for long notes.':'Hold the matching sign at the line.<br>Hold through tails; release between notes.';}
$('keys').onclick=async()=>{inputMode('keys');cameraOn=false;await fetch('/api/camera/stop',{method:'POST'});$('preview').hidden=true;poseDrawing($('skeleton'),[]);};
$('camera').onclick=async()=>{inputMode('hands');try{await syncTrackerSigns(setupPhase()?difficulty:runDifficulty,setupPhase()?chosenSigns:runSigns);await fetch('/api/camera/start',{method:'POST'});cameraOn=true;}catch{$('cameraStatus').textContent='Server unavailable';}};
document.addEventListener('keydown',e=>{
  if(phase==='editor'|| $('signsDialog').open || $('calibrationDialog').open || $('library').open || e.target.tagName==='INPUT')return;
  const key=e.key.toLowerCase();if(e.repeat)return;
  if(e.target.tagName==='BUTTON'&&!keys.includes(key))return;
  if(key==='escape'){e.preventDefault();if(phase==='menu')showTracks();else if(phase==='tracks')menu();else pause();}else if(key==='r'){if(['playing','paused','finished'].includes(phase))start();}else if(key==='q')menu();else if(key===' '){e.preventDefault();phase==='playing'?pause():primaryAction();}else if(mode==='keys'&&keys.includes(key)){e.preventDefault();pressedKeys.add(key);hit(keys.indexOf(key));}
});
document.addEventListener('keyup',e=>pressedKeys.delete(e.key.toLowerCase()));
window.addEventListener('blur',()=>{pressedKeys.clear();pressedPointers.clear();if(phase==='playing')pause();});
canvas.addEventListener('pointerdown',e=>{
  if(mode!=='keys')return;
  const r=canvas.getBoundingClientRect(),lane=Math.min(3,Math.max(0,Math.floor((e.clientX-r.left)/r.width*4)));
  canvas.setPointerCapture(e.pointerId);pressedPointers.set(e.pointerId,lane);hit(lane,null,'pointer');
});
for(const type of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(type,e=>pressedPointers.delete(e.pointerId));
async function poll(){
  if(pollBusy||!cameraOn)return;pollBusy=true;
  try{
    const state=await fetch('/api/state').then(r=>r.json());$('cameraStatus').textContent=state.status;
    $('recognized').textContent=state.sign==='No hands'?'Show both hands':state.sign;
    $('preview').hidden=state.status!=='Tracking';if(state.status==='Tracking')$('preview').src='/api/preview?t='+Date.now();
    if($('calibrationDialog').open){
      $('calibrationPreview').src='/api/preview?t='+Date.now();
      poseDrawing($('calibrationSkeleton'),state.hands,'#ad9bff',false);
      calibrationState(state);
    }
    poseDrawing($('skeleton'),state.hands,'#ad9bff',false);
    const sign=state.sign, now=performance.now();trackedSign=sign;trackedAt=now;
    if(!signs.includes(sign)){candidate='';latched='';}
    else{if(sign!==candidate){candidate=sign;candidateAt=now;latched='';}
      if(now-candidateAt>=80&&latched!==sign&&phase==='playing'){
        const note=notes.find(n=>!n.done&&!n.started&&n.sign===sign&&Math.abs(n.time-elapsed)<=.23);
        if(note){hit(note.lane,sign,'hands');latched=sign;}
      }}
    $('connection').textContent=state.status==='Tracking'?'HAND TRACKING LIVE':'LOCAL SESSION';
  }catch{$('cameraStatus').textContent='Tracking server disconnected';}finally{pollBusy=false;}
}
setInterval(poll,65);
function draw(now){
  const dt=Math.min(.1,(now-lastFrame)/1000);lastFrame=now;
  if(phase==='playing'){
    if(runTrack.imported){
      if(!songStarted){elapsed=playOffset+audio.currentTime-playClock;if(elapsed>=countInLength()){songStarted=true;elapsed=countInLength();playSong();}}
      else elapsed=countInLength()+songAudio.currentTime;
    }else{elapsed=playOffset+audio.currentTime-playClock;scheduleBeat();}
    if(elapsed<countInLength()){
      while(countdownBeat<5&&countdownBeat*beatLength()<=elapsed+.09){
        sound(audio.currentTime+Math.max(0,countdownBeat*beatLength()-elapsed),countdownBeat===4?880:660,.09,'triangle',.25);countdownBeat++;
      }
    }
    updateHolds(now);
    if(elapsed>=runDuration()-.02||(runTrack.imported&&songStarted&&songAudio.ended)){phase='finished';stopAudio();overlay('Track complete.',`${score.toLocaleString()} points · ${best} best combo · ${$('accuracy').textContent}% accuracy`,'Play again','NICE SESSION');}
  }
  const r=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1;
  if(canvas.width!==Math.round(r.width*ratio)||canvas.height!==Math.round(r.height*ratio)){canvas.width=Math.round(r.width*ratio);canvas.height=Math.round(r.height*ratio);}
  ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,r.width,r.height);
  const w=r.width,h=r.height,laneW=w/4,hitY=h-125,speed=(hitY+40)/3;
  for(let lane=0;lane<4;lane++){
    const x=(lane+.5)*laneW;ctx.strokeStyle='#25212b';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(lane*laneW,0);ctx.lineTo(lane*laneW,h);ctx.stroke();
    if(flash[lane]>now){const g=ctx.createLinearGradient(0,hitY-160,0,hitY+50);g.addColorStop(0,'transparent');g.addColorStop(1,colors[lane]+'33');ctx.fillStyle=g;ctx.fillRect(lane*laneW,hitY-160,laneW,210);}
    ctx.strokeStyle='#51465d';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(lane*laneW,hitY);ctx.lineTo((lane+1)*laneW,hitY);ctx.stroke();
    ctx.fillStyle='#08090b';ctx.beginPath();ctx.arc(x,hitY,23,0,Math.PI*2);ctx.fill();ctx.strokeStyle=colors[lane];ctx.lineWidth=1.5;ctx.stroke();
    ctx.fillStyle=colors[lane];ctx.font='12px Courier New';ctx.textAlign='center';ctx.fillText(mode==='keys'?keys[lane].toUpperCase():'◇',x,hitY+4);
  }
  for(const note of notes){if(note.done)continue;
    const y=note.started?hitY:hitY-(note.time-elapsed)*speed;
    const tailY=hitY-(note.time+note.duration-elapsed)*speed;
    if(y < -40||(!note.started&&y>h))continue;
    if(note.duration){
      const x=(note.lane+.5)*laneW;
      ctx.strokeStyle=colors[note.lane]+(note.started?'ff':'99');ctx.lineWidth=4;
      ctx.beginPath();ctx.moveTo(x,y-18);ctx.lineTo(x,Math.min(y-18,tailY));ctx.stroke();
      ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x-7,tailY);ctx.lineTo(x+7,tailY);ctx.stroke();
    }
    const x=(note.lane+.5)*laneW;ctx.fillStyle=colors[note.lane]+'22';ctx.strokeStyle=colors[note.lane];ctx.lineWidth=2;
    ctx.beginPath();ctx.roundRect(x-laneW*.34,y-18,laneW*.68,36,4);ctx.fill();ctx.stroke();
    ctx.fillStyle=colors[note.lane];ctx.font=`${laneW<95?9:11}px Courier New`;ctx.textAlign='center';ctx.fillText(note.sign.toUpperCase(),x,y+4);
  }
  const upcoming=notes.find(n=>!n.done)||{sign:setupPhase()?chosenSigns[0]:runSigns[0]};
  if($('nextSign').textContent!==upcoming.sign){$('nextSign').textContent=upcoming.sign;poseDrawing($('pose'),data.signs[upcoming.sign][0]?.hands||[]);}
  $('labels').innerHTML=keys.map((key,lane)=>{const next=notes.find(n=>!n.done&&n.lane===lane);return `<div style="color:${colors[lane]}">${next?.sign||(setupPhase()?selectedSignPool(difficulty,chosenSigns):runSigns).filter((_,i)=>i%4===lane)[0]||'?'}<small>${mode==='keys'?key.toUpperCase():'HAND SIGN'}</small></div>`;}).join('');
  $('countdown').hidden=phase!=='playing'||elapsed>=countInLength();
  if(!$('countdown').hidden)$('countdownNumber').textContent=5-Math.floor(elapsed/beatLength());
  const musicTime=Math.max(0,elapsed-countInLength()),total=runTrack.duration||60;
  $('progress').style.width=Math.min(100,musicTime/total*100)+'%';$('time').textContent=formatTime(Math.min(total,musicTime));
  if(now>feedbackUntil)$('judgement').textContent='';requestAnimationFrame(draw);
}
poseDrawing($('pose'),data.signs.serpent[0]?.hands||reference.signs.serpent[0].hands);statistics();requestAnimationFrame(draw);

const calibrationSigns = [...signOrder];
let calibrationIndex = 0, recording = false, recordingPending = false, calibrationDone = false;
function prepareCalibration(){
  const sign = calibrationSigns[calibrationIndex];
  $('calibrationTitle').textContent = `${sign.toUpperCase()} / ${calibrationIndex+1} of ${calibrationSigns.length}`;
  $('calibrationSign').textContent = sign;
  poseDrawing($('calibrationPose'), reference.signs[sign][0]?.hands || []);
  $('calibrationTimer').textContent = '15.0 seconds';$('calibrationCount').textContent = '0 samples';
  $('calibrationProgress').style.width = '0%';$('recordCalibration').hidden = false;
  $('recordCalibration').disabled = true;$('recordCalibration').textContent = 'Start 15-second recording';
  $('nextCalibration').hidden = true;calibrationDone = false;
  $('calibrationStatus').textContent='Make the shown sign, then start recording. Browsing does not clear samples.';
  updateCalibrationNavigation();
}
function calibrationState(state){
  const c = state.calibration;
  if(recording && c.status === 'recording'){
    $('calibrationTimer').textContent = `${c.remaining.toFixed(1)} seconds`;
    $('calibrationCount').textContent = `${c.count} samples`;
    $('calibrationProgress').style.width = `${(15-c.remaining)/15*100}%`;
    $('calibrationStatus').textContent = state.hands.length === 2 ? 'Recording every detected two-hand frame. Move up and down, rotate and tilt slowly.' : 'Both hands must be visible. No sample captured for this frame.';
  }else if(recording && c.status !== 'recording'){
    recording = false;calibrationDone = true;
    $('calibrationTimer').textContent = 'Finished';$('calibrationCount').textContent = `${c.count} samples`;
    $('calibrationProgress').style.width = '100%';$('recordCalibration').hidden = false;
    $('recordCalibration').textContent = 'Record this sign again';$('recordCalibration').disabled = state.status !== 'Tracking';
    $('nextCalibration').hidden = c.count === 0 || c.status === 'error';
    $('nextCalibration').textContent = calibrationIndex === calibrationSigns.length-1 ? 'Finish calibration' : 'Next sign';
    $('calibrationStatus').textContent = c.error || (c.count ? `Saved ${c.count} new samples. Ready for the next sign.` : 'No samples captured. Keep both hands visible and record this sign again.');
    fetch('/assets/hand_signs.json',{cache:'no-store'}).then(r=>r.json()).then(updated=>{data.signs=updated.signs;refreshLibrary();}).catch(()=>{});
  }else if(!recordingPending){
    $('recordCalibration').disabled = state.status !== 'Tracking';
    if(!calibrationDone)$('calibrationStatus').textContent = state.status === 'Tracking' ? 'Make the shown sign, then start recording. Its old samples will be cleared.' : state.status;
  }
  updateCalibrationNavigation();
}
$('calibrate').onclick = async()=>{
  if(phase==='playing')pause();
  calibrationIndex=0;recording=false;prepareCalibration();$('calibrationDialog').showModal();
  inputMode('hands');
  try{await syncTrackerSigns(setupPhase()?difficulty:runDifficulty,setupPhase()?chosenSigns:runSigns);await fetch('/api/camera/start',{method:'POST'});cameraOn=true;}catch{$('calibrationStatus').textContent='Camera server unavailable';}
};
$('recordCalibration').onclick = async()=>{
  recordingPending=true;$('recordCalibration').disabled=true;updateCalibrationNavigation();
  try{
    const response=await fetch('/api/calibration/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sign:calibrationSigns[calibrationIndex]})});
    if(!response.ok)throw new Error((await response.json()).error);
    recording=true;calibrationDone=false;$('recordCalibration').hidden=true;$('nextCalibration').hidden=true;
  }catch(error){$('calibrationStatus').textContent=error.message;$('recordCalibration').disabled=false;}
  finally{recordingPending=false;updateCalibrationNavigation();}
};
$('nextCalibration').onclick=()=>{if(calibrationIndex===calibrationSigns.length-1){$('calibrationDialog').close();}else{navigateCalibration(1);}};
$('closeCalibration').onclick=()=>{if(!recordingPending)$('calibrationDialog').close();};
$('calibrationDialog').addEventListener('cancel',event=>{if(recordingPending)event.preventDefault();});
$('calibrationDialog').addEventListener('close',async()=>{
  if(recording){await fetch('/api/calibration/cancel',{method:'POST'});recording=false;}
  const updated=await fetch('/assets/hand_signs.json',{cache:'no-store'}).then(r=>r.json());data.signs=updated.signs;refreshLibrary();
});

function updateCalibrationNavigation(){
  const busy=recording||recordingPending;
  $('previousCalibrationSign').disabled=busy;
  $('nextCalibrationSign').disabled=busy;
}
function navigateCalibration(direction){
  if(recording||recordingPending)return;
  calibrationIndex=(calibrationIndex+direction+calibrationSigns.length)%calibrationSigns.length;
  prepareCalibration();
}
$('previousCalibrationSign').onclick=()=>navigateCalibration(-1);
$('nextCalibrationSign').onclick=()=>navigateCalibration(1);
document.addEventListener('keydown',event=>{
  if(!$('calibrationDialog').open||!['ArrowLeft','ArrowRight'].includes(event.key))return;
  event.preventDefault();navigateCalibration(event.key==='ArrowLeft'?-1:1);
});
let calibrationTouch=null;
$('calibrationCarousel').addEventListener('touchstart',event=>{
  if(event.touches.length!==1||event.target.closest('button')){calibrationTouch=null;return;}
  calibrationTouch={x:event.touches[0].clientX,y:event.touches[0].clientY};
},{passive:true});
$('calibrationCarousel').addEventListener('touchend',event=>{
  if(!calibrationTouch)return;
  const touch=event.changedTouches[0],dx=touch.clientX-calibrationTouch.x,dy=touch.clientY-calibrationTouch.y;
  calibrationTouch=null;
  if(Math.abs(dx)>50&&Math.abs(dx)>Math.abs(dy)*1.5)navigateCalibration(dx<0?1:-1);
},{passive:true});
$('calibrationCarousel').addEventListener('touchcancel',()=>{calibrationTouch=null;},{passive:true});

updateTrackInfo();menu();

function renderSignWheel(){
  const wheel=$('signWheel');wheel.querySelectorAll('.wheel-slot').forEach(node=>node.remove());
  $('wheelCenter').textContent=`${difficulty} active`;
  chosenSigns.forEach((sign,index)=>{
    const angle=-Math.PI/2+index*Math.PI*2/5;
    const button=document.createElement('button');button.className='wheel-slot';
    button.style.left=`${50+36*Math.cos(angle)}%`;button.style.top=`${50+36*Math.sin(angle)}%`;
    button.classList.toggle('active-slot',index===activeSignSlot);button.classList.toggle('inactive-slot',index>=difficulty);
    button.setAttribute('aria-pressed',String(index===activeSignSlot));button.setAttribute('aria-label',`Slot ${index+1}: ${sign}`);
    const number=document.createElement('small');number.textContent=`0${index+1}`;
    const drawing=document.createElement('canvas');drawing.width=150;drawing.height=90;
    const name=document.createElement('span');name.textContent=sign;button.append(number,drawing,name);
    poseDrawing(drawing,reference.signs[sign][0]?.hands||[]);
    button.onclick=()=>{activeSignSlot=index;renderSignWheel();};wheel.append(button);
  });
  $('signChoices').replaceChildren();
  for(const sign of signOrder){
    const button=document.createElement('button');button.textContent=sign;button.classList.toggle('selected',chosenSigns[activeSignSlot]===sign);
    button.onclick=()=>{
      const previous=chosenSigns.indexOf(sign),old=chosenSigns[activeSignSlot];
      if(previous>=0)chosenSigns[previous]=old;chosenSigns[activeSignSlot]=sign;
      try{localStorage.setItem('signs-selection',JSON.stringify(chosenSigns));}catch{}
      updateDifficulty();renderSignWheel();
      if(setupPhase())syncTrackerSigns(difficulty).catch(error=>{$('signSelectionStatus').textContent=error.message;});
    };$('signChoices').append(button);
  }
}
$('signsButton').onclick=()=>{if(phase==='playing')pause();renderSignWheel();$('signsDialog').showModal();};
$('closeSigns').onclick=()=>$('signsDialog').close();
setInterval(async()=>{
  if(phase!=='tracks'||importing)return;
  try{
    const old=JSON.stringify(importedTracks);await refreshImportedTracks();
    if(phase==='tracks'&&JSON.stringify(importedTracks)!==old){trackChoices=mergeTracks(tracks,importedTracks);renderTrackPage();}
    const jobs=await fetch('/api/songs/status').then(r=>r.json());
    const busy=jobs.filter(j=>['queued','analyzing'].includes(j.status));
    const errors=jobs.filter(j=>j.status==='error');
    $('importStatus').textContent=busy.length?`${busy.length} song(s) processing / ${busy[0].message}`:errors.length?`${errors[errors.length-1].filename}: ${errors[errors.length-1].message}`:importedTracks.length?'Songs folder synced. Drop an MP3 into songs to add a track.':'';
  }catch{}
},2000);

const mapEditor=createMapEditor({
  getTracks:async()=>{await refreshImportedTracks();return importedTracks;},
  getSigns:()=>[...chosenSigns],
  onExit:()=>menu(),
  onSave:async track=>{await refreshImportedTracks();if(selectedTrack.id===track.id){selectedTrack=importedTracks.find(row=>row.id===track.id)||track;updateTrackInfo();}},
});
$('mapEditorButton').onclick=()=>{stopAudio();phase='editor';mapEditor.open(selectedTrack.id);};
