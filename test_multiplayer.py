import asyncio,json,sys,math
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent))
from aiohttp.test_utils import TestServer, TestClient
import server
async def main():
 async with TestServer(server.app) as srv:
  async with TestClient(srv) as c:
   sockets=[]
   for i in range(8):
    ws=await c.ws_connect('/ws?room=ABC234&name=user'+str(i));sockets.append(ws);m=await ws.receive_json();assert m['type']=='welcome';
   extra=await c.ws_connect('/ws?room=ABC234&name=extra');assert (await extra.receive_json())['type']=='error';await extra.close()
   a=await sockets[0].receive_json();b=await sockets[1].receive_json();assert len(a['players'])==8 and len(b['players'])==8;assert a['foods']==b['foods'];assert a['items']==b['items']
   own=a['players'][0]['id'];first=server.rooms['ABC234']['players'][own];first['inventory']=['slow','grow'];old=first['length'];await sockets[0].send_json({'type':'use','index':0});await asyncio.sleep(.1);assert first['effects']['slow']>0 and first['inventory']==['grow'];await sockets[0].send_json({'type':'use','index':0});await asyncio.sleep(.1);assert first['length']>old
   await sockets[1].close();await asyncio.sleep(.1);assert len(server.rooms['ABC234']['players'])==7
   for ws in sockets:await ws.close()
   print('PASS: 8 participants, ninth rejected, shared food/items, item effects, disconnect cleanup')
asyncio.run(main())
