import asyncio, itertools, json, math, os, random, re, secrets, time
from aiohttp import web, WSMsgType
WORLD=3400; TICK=.05; rooms={}; FOOD_IDS=itertools.count(1)
COLORS=['#60e8cd','#ff81b0','#ac83ff','#5cbcff','#ffda5f','#ffa162','#ec80ff','#70ed87','#ff6d76','#58dce9','#f4a3ce','#98a7ff']
TYPES={'shield':5,'magnet':7,'speed':4,'slow':5,'double':8,'grow':0,'ghost':4,'shrink':6,'bomb':0}
def food(x=None,y=None):
 v=random.choices([1,2,3],[70,24,6])[0];return {'id':next(FOOD_IDS),'x':x if x is not None else random.uniform(30,WORLD-30),'y':y if y is not None else random.uniform(30,WORLD-30),'value':v,'r':{1:3.7,2:5,3:7.1}[v],'color':random.choice(COLORS),'phase':random.random()*6.28}
def item(x=None,y=None):return {'x':x if x is not None else random.uniform(50,WORLD-50),'y':y if y is not None else random.uniform(50,WORLD-50),'type':random.choice(list(TYPES))}
def dist2(a,b):return (a['x']-b['x'])**2+(a['y']-b['y'])**2
def radius(p):return (8+min(10,(p['score']//100)*.6))*(.65 if p['effects'].get('shrink',0)>0 else 1)
def make_player(name,color):
 x=random.uniform(500,WORLD-500);y=random.uniform(500,WORLD-500);angle=math.atan2(WORLD/2-y,WORLD/2-x)+random.uniform(-.65,.65)
 return {'x':x,'y':y,'angle':angle,'target':angle,'color':color,'name':name,'trail':[{'x':x-i*5*math.cos(angle),'y':y-i*5*math.sin(angle)} for i in range(30)],'length':145.,'score':0,'alive':True,'inventory':[],'effects':{**{k:0 for k in TYPES if k not in ('grow','bomb')},'reverse':0},'deadReason':'','boosting':False,'speed':160,'survival':0.,'viewW':1100,'viewH':850,'invVersion':0,'worldNext':0.,'lastRequest':None,'bombPulse':0}
def new_room():return {'players':{},'foods':[food() for _ in range(680)],'items':[item() for _ in range(35)],'last':time.monotonic()}
def project(p,a,b):
 dx=b['x']-a['x'];dy=b['y']-a['y'];d=dx*dx+dy*dy;t=max(0,min(1,((p['x']-a['x'])*dx+(p['y']-a['y'])*dy)/d)) if d else 0
 return (p['x']-a['x']-dx*t)**2+(p['y']-a['y']-dy*t)**2
def step(room,dt):
 players=room['players'];foods=room['foods'];items=room['items']
 for p in list(players.values()):
  if not p['alive']:continue
  p['survival']+=dt
  for k in p['effects']:p['effects'][k]=max(0,p['effects'][k]-dt)
  p['bombPulse']=max(0,p['bombPulse']-dt)
  target=(math.pi-p['target'])%math.tau if p['effects']['reverse']>0 else p['target'];d=(target-p['angle']+math.pi)%math.tau-math.pi;p['angle']+=max(-4.5*dt,min(4.5*dt,d));slow=any(q is not p and q['alive'] and q['effects']['slow']>0 and dist2(p,q)<=300**2 for q in players.values())
  speed=160*(1.55 if p['effects']['speed'] else 1)*(.55 if slow else 1);p['motionSpeed']=speed;p['x']+=math.cos(p['angle'])*speed*dt;p['y']+=math.sin(p['angle'])*speed*dt;p['boosting']=p['effects']['speed']>0
  p['trail'].insert(0,{'x':p['x'],'y':p['y']});length=0
  for j in range(1,len(p['trail'])):
   a,b=p['trail'][j-1:j+1];length+=math.hypot(a['x']-b['x'],a['y']-b['y'])
   if length>p['length']:del p['trail'][j+1:];break
  if p['x']<14 or p['y']<14 or p['x']>WORLD-14 or p['y']>WORLD-14:p['alive']=False;p['deadReason']='wall';continue
  remaining=[];magnet=p['effects']['magnet']>0
  for f in foods:
   dx=p['x']-f['x'];dy=p['y']-f['y'];d2=dx*dx+dy*dy
   if magnet and 1<d2<145**2:
    d=math.sqrt(d2);move=min(d,260*dt);f['x']+=dx/d*move;f['y']+=dy/d*move;dx=p['x']-f['x'];dy=p['y']-f['y'];d2=dx*dx+dy*dy
   if d2<(radius(p)+5+f['r'])**2:
    before=p['score']//100;p['score']+=f['value']*10*(2 if p['effects']['double'] else 1);p['length']+=f['value']*4.5+22*(p['score']//100-before)
   else:remaining.append(f)
  foods[:]=remaining
  if len(p['inventory'])<2:
   for it in items[:]:
    if dist2(p,it)<(radius(p)+17)**2:p['inventory'].append(it['type']);p['invVersion']+=1;items.remove(it);break
 bounds={}
 for q in players.values():
  if q['alive'] and q['trail']:
   xs=[v['x'] for v in q['trail']];ys=[v['y'] for v in q['trail']];bounds[id(q)]=(min(xs),max(xs),min(ys),max(ys))
 for p in list(players.values()):
  if not p['alive'] or p['effects']['shield'] or p['effects']['ghost']:continue
  for q in list(players.values()):
   if p is q or not q['alive'] or q['effects']['ghost'] or id(q) not in bounds:continue
   x0,x1,y0,y1=bounds[id(q)];r=radius(p)+radius(q)
   if p['x']<x0-r or p['x']>x1+r or p['y']<y0-r or p['y']>y1+r:continue
   if any(project(p,q['trail'][i-1],q['trail'][i])<(radius(p)+radius(q))**2 for i in range(1,len(q['trail']))):p['alive']=False;p['deadReason']='worm';break
 for p in players.values():
  if not p['alive'] and not p.get('dropped'):
   p['dropped']=True
   for pt in p['trail'][::3]:
    if len(foods)<1000:foods.append(food(pt['x'],pt['y']))
 while len(foods)<680:foods.append(food())
 while len(items)<35:items.append(item())
async def broadcast_loop(app):
 while True:
  await asyncio.sleep(TICK)
  for code,room in list(rooms.items()):
   if not room['players']:
    if time.monotonic()-room['last']>60:rooms.pop(code,None)
    continue
   now=time.monotonic();dt=min(.1,now-room['last']);room['last']=now;step(room,dt)
   ordered=sorted(room['players'].items(),key=lambda z:z[1]['score'],reverse=True)
   players=[]
   for pid,p in ordered:
    wire={k:v for k,v in p.items() if k not in ('target','effects','inventory','dropped','deadReason','viewW','viewH','trail','invVersion','worldNext','lastRequest')}
    wire['visualEffects']={k:round(v,1) for k,v in p['effects'].items() if v>0};wire['ghost']=p['effects']['ghost']>0;wire['shrink']=p['effects']['shrink']>0;wire['id']=pid;wire['x']=round(p['x'],1);wire['y']=round(p['y'],1);wire['angle']=round(p['angle'],3)
    trail=p['trail'];stride=max(1,math.ceil(len(trail)/160));sample=trail[::stride]
    if sample and sample[-1] is not trail[-1]:sample.append(trail[-1])
    wire['trail']=[{'x':round(pt['x'],1),'y':round(pt['y'],1)} for pt in sample];players.append(wire)
   world_due=any(p['worldNext']<=now for p in room['players'].values())
   packed_food=[{**f,'x':round(f['x'],1),'y':round(f['y'],1),'phase':round(f['phase'],2)} for f in room['foods']] if world_due else []
   packed_items=[{**it,'x':round(it['x'],1),'y':round(it['y'],1)} for it in room['items']] if world_due else []
   for pid,p in list(room['players'].items()):
    ws=app['sockets'].get(pid)
    if not ws or ws.closed:continue
    msg={'type':'state','players':players,'inventory':list(p['inventory']),'invVersion':p['invVersion'],'effects':dict(p['effects']),'alive':p['alive'],'elapsed':p['survival'],'reason':p['deadReason'],'rank':next((i+1 for i,(x,_) in enumerate(ordered) if x==pid),1)}
    if p['worldNext']<=now:
     half_w=max(400,min(2200,p['viewW']/2+260));half_h=max(400,min(2200,p['viewH']/2+260))
     nearby=lambda obj:abs(obj['x']-p['x'])<half_w and abs(obj['y']-p['y'])<half_h
     msg['foods']=[f for f in packed_food if nearby(f)];msg['items']=[it for it in packed_items if nearby(it)];p['worldNext']=now+.2
    queue=app['queues'].get(pid)
    if queue is not None:
     if queue.full():
      try:queue.get_nowait()
      except asyncio.QueueEmpty:pass
     queue.put_nowait(json.dumps(msg,separators=(',',':')))
async def send_states(ws,queue):
 try:
  while not ws.closed:await ws.send_str(await queue.get())
 except (ConnectionError,asyncio.CancelledError):pass
async def socket(request):
 code=request.query.get('room','').upper();name=request.query.get('name','꼬물이').strip()[:12] or '꼬물이';color=request.query.get('color','')
 if not re.fullmatch(r'[A-Z0-9]{6}',code):raise web.HTTPBadRequest(text='잘못된 방 코드')
 ws=web.WebSocketResponse(heartbeat=20,max_msg_size=2048);await ws.prepare(request);room=rooms.get(code)
 if room is None:room=rooms[code]=new_room()
 if len(room['players'])>=8:await ws.send_json({'type':'error','message':'방이 가득 찼어요. 최대 8명까지 참여할 수 있어요.'});await ws.close();return ws
 pid=secrets.token_urlsafe(12);p=make_player(name,color if color in COLORS else COLORS[0]);room['players'][pid]=p;room['last']=time.monotonic();request.app['sockets'][pid]=ws
 await ws.send_json({'type':'welcome','id':pid,'room':code})
 queue=asyncio.Queue(maxsize=1);request.app['queues'][pid]=queue;sender=asyncio.create_task(send_states(ws,queue))
 try:
  async for msg in ws:
   if msg.type!=WSMsgType.TEXT:continue
   try:data=json.loads(msg.data)
   except (ValueError,TypeError):continue
   if not isinstance(data,dict):continue
   if data.get('type')=='aim':
    angle=data.get('angle');
    if isinstance(angle,(int,float)) and math.isfinite(angle):p['target']=angle%math.tau
    for field,key in [('viewW','width'),('viewH','height')]:
     size=data.get(key)
     if isinstance(size,(int,float)) and math.isfinite(size):p[field]=max(200,min(4000,size))
   elif data.get('type')=='use':
    idx=data.get('index');inv=p['inventory'];req=data.get('requestId');expected=data.get('itemType')
    if isinstance(req,int) and p['lastRequest'] and p['lastRequest']['requestId']==req:
     await ws.send_json(p['lastRequest']);continue
    ok=p['alive'] and type(idx) is int and 0<=idx<len(inv) and (expected is None or expected==inv[idx]);k=None
    if ok:
     k=inv.pop(idx);p['invVersion']+=1
     if k=='grow':p['length']+=110
     elif k=='bomb':
      p['bombPulse']=.65
      for other in room['players'].values():
       if other is not p and other['alive'] and not other['effects']['shield'] and dist2(p,other)<=260**2:other['effects']['reverse']=5
     else:p['effects'][k]=TYPES[k]
    ack={'type':'itemResult','requestId':req,'ok':ok,'itemType':k,'inventory':list(inv),'invVersion':p['invVersion'],'effects':dict(p['effects']),'length':p['length']}
    if isinstance(req,int):p['lastRequest']=ack
    await ws.send_json(ack)
 finally:
  room['players'].pop(pid,None);request.app['sockets'].pop(pid,None);request.app['queues'].pop(pid,None);sender.cancel();await sender;room['last']=time.monotonic()
 return ws
async def home(request):return web.FileResponse(os.path.join(os.path.dirname(__file__),'public','index.html'))
async def health(request):return web.json_response({'ok':True})
async def start(app):app['loop_task']=asyncio.create_task(broadcast_loop(app))
async def cleanup(app):
 app['loop_task'].cancel()
 try:await app['loop_task']
 except asyncio.CancelledError:pass
app=web.Application();app['sockets']={};app['queues']={};app.router.add_get('/',home);app.router.add_get('/ws',socket);app.router.add_get('/health',health);app.on_startup.append(start);app.on_cleanup.append(cleanup)
if __name__=='__main__':web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')))
