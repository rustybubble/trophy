import test from 'node:test';
import assert from 'node:assert/strict';
import {sourcePoint,moveCorner} from '../web/corner-picker/geometry.mjs';

test('clicks map from a resized preview to the full source frame',()=>{
  const point=sourcePoint(410,275,{left:90,top:95,width:640,height:360},1920,1080);
  assert.deepEqual(point,[960,540]);
  assert.deepEqual(sourcePoint(250,185,{left:90,top:95,width:320,height:180},1920,1080),point);
});

test('portrait frames and clicks beyond the boundary stay inside source pixels',()=>{
  assert.deepEqual(sourcePoint(180,320,{left:0,top:0,width:360,height:640},1080,1920),[540,960]);
  assert.deepEqual(sourcePoint(1000,-10,{left:0,top:0,width:360,height:640},1080,1920),[1079,0]);
});

test('adjusting a selected corner preserves the other physical corner labels',()=>{
  const original=[[10,20],[30,40],[50,60],[70,80]];
  assert.deepEqual(moveCorner(original,1,[32,42]),[[10,20],[32,42],[50,60],[70,80]]);
  assert.deepEqual(original,[[10,20],[30,40],[50,60],[70,80]]);
  assert.deepEqual(moveCorner(original,4,[90,100]),original);
});
