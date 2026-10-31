"""Generate the original waveform icon using only the Python standard library."""
from pathlib import Path
import math
import struct
import zlib


def png(size):
    rows=[]
    heights=(.16,.32,.50,.65,.43,.24)
    for y in range(size):
        row=bytearray([0])
        for x in range(size):
            u,v=(x+.5)/size,(y+.5)/size
            dx,dy=max(abs(u-.5)-.32,0),max(abs(v-.5)-.32,0)
            alpha=max(0,min(1,(.18-math.hypot(dx,dy))*size))
            color=(15+int(v*10),27+int(v*10),39+int(v*12))
            for i,h in enumerate(heights):
                cx=.225+i*.11
                d=math.hypot(u-cx,max(abs(v-.5)-(h/2-.035),0))
                if d<.035:
                    color=(int(111+40*v),int(218+20*v),int(187+30*v))
            row.extend((*color,round(alpha*255)))
        rows.append(row)
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',size,size,8,6,0,0,0))+
            chunk(b'IDAT',zlib.compress(b''.join(rows),9))+chunk(b'IEND',b''))


def main():
    folder=Path(__file__).resolve().parents[1]/'assets';folder.mkdir(exist_ok=True)
    sizes=(16,32,48,256);images=[png(s) for s in sizes]
    offset=6+16*len(sizes);entries=[]
    for size,data in zip(sizes,images):
        entries.append(struct.pack('<4B2H2I',size%256,size%256,0,0,1,32,len(data),offset));offset+=len(data)
    (folder/'app.ico').write_bytes(struct.pack('<3H',0,1,len(sizes))+b''.join(entries)+b''.join(images))
    (folder/'app.png').write_bytes(png(48))


if __name__=='__main__':main()
