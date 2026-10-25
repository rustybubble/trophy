// Decode the actual marked frame, ignoring an older frame already queued for paint.
// Seeking a few microseconds inside its interval avoids boundary round-off.
export async function decodeFrameAt(video,time,{timeoutMs=8000}={}){
  if(!Number.isFinite(time)||time<0)throw Error('Invalid marked source time.');
  if(!video.seeking&&Number.isFinite(video.presentedFramePTS)&&Math.abs(video.presentedFramePTS-time)<.001)return video.presentedFramePTS;
  if(!video.requestVideoFrameCallback)throw Error('Proof export requires presented-frame timestamp support.');
  return new Promise((resolve,reject)=>{
    let callback,done=false;
    const finish=(value,error)=>{if(done)return;done=true;clearTimeout(timeout);video.cancelVideoFrameCallback(callback);error?reject(error):resolve(value);};
    const timeout=setTimeout(()=>finish(null,Error(`Could not decode marked source frame ${time.toFixed(6)} s exactly.`)),timeoutMs);
    const onFrame=(_now,meta)=>{
      video.presentedFramePTS=meta.mediaTime;
      if(Math.abs(meta.mediaTime-time)<.001)finish(meta.mediaTime);
      else callback=video.requestVideoFrameCallback(onFrame);
    };
    callback=video.requestVideoFrameCallback(onFrame);
    video.currentTime=time+.00001;
  });
}
