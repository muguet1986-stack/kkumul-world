import asyncio, json, math, os, random, re, secrets, time
from aiohttp import web, WSMsgType
WORLD=3400; TICK=.05; rooms={}
COLORS=['#60e8cd','#ff81b0','#ac83ff','#5cbcff','#ffda5f','#ffa162','#ec80ff','#70ed87','#ff6d76','#58dce9','#f4a3ce','#98a7ff']
TYPES={'shield':5,'magnet':7,'speed':4,'slow':5,'double':8,'grow':0}
def food(x=None,y=None):
 v=random.choices([1,2,3],[70,24,6])[0];return {'x':x if x is not None else random.uniform(30,WORLD-30),'y':y if y is not None else random.uniform(30,WORLD-30),'value':v,'r':{1:3.7,2:5,3:7.1}[v],'color':random.choice(COLORS),'phase':random.random()*6.28}
def item(x=None,y=None):return {'x':x if x is not None else random.uniform(50,WORLD-50),'y':y if y is not None else random.uniform(50,WORLD-50),'type':random.choice(list(TYPES))}
def dist2(a,b):return (a['x']-b['x'])**2+(a['y']-b['y'])**2
def radius(p):return 8+min(10,(p['score']//100)*.6)
def make_player(name,color):
 x=random.uniform(500,WORLD-500);y=random.uniform(500,WORLD-500);angle=math.atan2(WORLD/2-y,WORLD/2-x)+random.uniform(-.65,.65)
 return {'x':x,'y':y,'angle':angle,'target':angle,'color':color,'name':name,'trail':[{'x':x-i*5*math.cos(angle),'y':y-i*5*math.sin(angle)} for i in range(30)],'length':145.,'score':0,'alive':True,'inventory':[],'effects':{k:0 for k in TYPES if k!='grow'},'deadReason':'','boosting':False,'speed':160,'survival':0.}
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
  d=(p['target']-p['angle']+math.pi)%math.tau-math.pi;p['angle']+=max(-4.5*dt,min(4.5*dt,d));slow=any(q is not p and q['alive'] and q['effects']['slow']>0 for q in players.values())
  speed=160*(1.55 if p['effects']['speed'] else 1)*(.55 if slow else 1);p['x']+=math.cos(p['angle'])*speed*dt;p['y']+=math.sin(p['angle'])*speed*dt;p['boosting']=p['effects']['speed']>0
  p['trail'].insert(0,{'x':p['x'],'y':p['y']});length=0
  for j in range(1,len(p['trail'])):
   a,b=p['trail'][j-1:j+1];length+=math.hypot(a['x']-b['x'],a['y']-b['y'])
   if length>p['length']:del p['trail'][j+1:];break
  if p['x']<14 or p['y']<14 or p['x']>WORLD-14 or p['y']>WORLD-14:p['alive']=False;p['deadReason']='wall';continue
  for f in foods[:]:
   d=math.sqrt(dist2(p,f))
   if p['effects']['magnet'] and 1<d<145:
    f['x']+=(p['x']-f['x'])/d*min(d,260*dt);f['y']+=(p['y']-f['y'])/d*min(d,260*dt)
   if dist2(p,f)<(radius(p)+5+f['r'])**2:
    before=p['score']//100;p['score']+=f['value']*10*(2 if p['effects']['double'] else 1);p['length']+=f['value']*4.5+22*(p['score']//100-before);foods.remove(f)
  if len(p['inventory'])<2:
   for it in items[:]:
    if dist2(p,it)<(radius(p)+17)**2:p['inventory'].append(it['type']);items.remove(it);break
 for p in list(players.values()):
  if not p['alive'] or p['effects']['shield']:continue
  for q in list(players.values()):
   if p is q or not q['alive']:continue
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
   players=[{'id':pid,**{k:v for k,v in p.items() if k not in ('target','effects','inventory','dropped','deadReason')}} for pid,p in ordered]
   for pid,p in list(room['players'].items()):
    ws=app['sockets'].get(pid)
    if not ws or ws.closed:continue
    msg={'type':'state','players':players,'foods':room['foods'],'items':room['items'],'inventory':p['inventory'],'effects':p['effects'],'alive':p['alive'],'elapsed':p['survival'],'reason':p['deadReason'],'rank':next((i+1 for i,(x,_) in enumerate(ordered) if x==pid),1)}
    try:await ws.send_str(json.dumps(msg,separators=(',',':')))
    except ConnectionError:pass
async def socket(request):
 code=request.query.get('room','').upper();name=request.query.get('name','꼬물이').strip()[:12] or '꼬물이';color=request.query.get('color','')
 if not re.fullmatch(r'[A-Z0-9]{6}',code):raise web.HTTPBadRequest(text='잘못된 방 코드')
 ws=web.WebSocketResponse(heartbeat=20,max_msg_size=2048);await ws.prepare(request);room=rooms.get(code)
 if room is None:room=rooms[code]=new_room()
 if len(room['players'])>=8:await ws.send_json({'type':'error','message':'방이 가득 찼어요. 최대 8명까지 참여할 수 있어요.'});await ws.close();return ws
 pid=secrets.token_urlsafe(12);p=make_player(name,color if color in COLORS else COLORS[0]);room['players'][pid]=p;room['last']=time.monotonic();request.app['sockets'][pid]=ws
 await ws.send_json({'type':'welcome','id':pid,'room':code})
 try:
  async for msg in ws:
   if msg.type!=WSMsgType.TEXT:continue
   try:data=json.loads(msg.data)
   except (ValueError,TypeError):continue
   if not isinstance(data,dict):continue
   if data.get('type')=='aim':
    angle=data.get('angle');
    if isinstance(angle,(int,float)) and math.isfinite(angle):p['target']=angle%math.tau
   elif data.get('type')=='use' and p['alive']:
    idx=data.get('index');inv=p['inventory']
    if type(idx) is int and 0<=idx<len(inv):
     k=inv.pop(idx)
     if k=='grow':p['length']+=110
     else:p['effects'][k]=TYPES[k]
 finally:
  room['players'].pop(pid,None);request.app['sockets'].pop(pid,None);room['last']=time.monotonic()
 return ws
async def home(request):return web.FileResponse(os.path.join(os.path.dirname(__file__),'public','index.html'))
async def health(request):return web.json_response({'ok':True})
async def start(app):app['loop_task']=asyncio.create_task(broadcast_loop(app))
async def cleanup(app):
 app['loop_task'].cancel()
 try:await app['loop_task']
 except asyncio.CancelledError:pass
app=web.Application();app['sockets']={};app.router.add_get('/',home);app.router.add_get('/ws',socket);app.router.add_get('/health',health);app.on_startup.append(start);app.on_cleanup.append(cleanup)
if __name__=='__main__':web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')))
