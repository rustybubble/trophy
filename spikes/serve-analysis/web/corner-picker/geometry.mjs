/** Map rendered image coordinates to the original, display-oriented source. */
export function sourcePoint(x, y, rect, width, height) {
  return [Math.max(0, Math.min(width-1, (x-rect.left)/rect.width*width)),
          Math.max(0, Math.min(height-1, (y-rect.top)/rect.height*height))];
}

export function moveCorner(points, index, point) {
  const next=points.map(p=>[...p]);
  if(index<next.length)next[index]=point;
  else if(next.length<4)next.push(point);
  return next;
}
