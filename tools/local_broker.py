"""Optional localhost MQTT broker when Docker is unavailable."""
import asyncio
from amqtt.broker import Broker

async def main():
    broker=Broker({'listeners':{'default':{'type':'tcp','bind':'127.0.0.1:1884'}},
                   'plugins':{'amqtt.plugins.authentication.AnonymousAuthPlugin':{'allow_anonymous':True}}})
    await broker.start()
    print('Local demo MQTT broker listening at 127.0.0.1:1884',flush=True)
    try: await asyncio.Event().wait()
    finally: await broker.shutdown()

if __name__=='__main__': asyncio.run(main())
