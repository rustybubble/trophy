import assert from 'node:assert/strict';
import {test} from 'node:test';
import {decodeFrameAt} from '../web/serves/frame-proof.js';

class Video{
  constructor({fps=240,emit=true}={}){this.callbacks=new Map();this.id=0;this.fps=fps;this.emit=emit;this.presentedFramePTS=0;}
  requestVideoFrameCallback(cb){this.callbacks.set(++this.id,cb);return this.id;}
  cancelVideoFrameCallback(id){this.callbacks.delete(id);}
  present(time){const callbacks=[...this.callbacks.values()];this.callbacks.clear();for(const cb of callbacks)cb(0,{mediaTime:time});}
  set currentTime(target){this.target=target;if(this.emit)queueMicrotask(()=>{this.present(0);queueMicrotask(()=>this.present(Math.floor(target*this.fps)/this.fps));});}
}

test('proof uses the marked 240 FPS frame rather than a previously queued frame',async()=>{
  const video=new Video();const time=106/240;
  assert.equal(await decodeFrameAt(video,time),time);
  assert.equal(video.callbacks.size,0);
});
test('the same source-boundary contract works at 60 FPS',async()=>{
  const video=new Video({fps:60});assert.equal(await decodeFrameAt(video,7.35),441/60);
});
test('an already presented paused frame does not require another seek',async()=>{
  const video=new Video();video.presentedFramePTS=.75;
  assert.equal(await decodeFrameAt(video,.75),.75);assert.equal(video.target,undefined);
});
test('an unavailable marked frame fails explicitly and cleans up callbacks',async()=>{
  const video=new Video({emit:false});
  await assert.rejects(decodeFrameAt(video,.75,{timeoutMs:10}),/exactly/);
  assert.equal(video.callbacks.size,0);
});
