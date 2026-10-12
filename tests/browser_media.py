from fractions import Fraction

import av


def repeat_browser_audio(fixture, target, seconds):
    with av.open(str(fixture)) as source:
        stream = source.streams.audio[0]
        packets = [bytes(packet) for packet in source.demux(stream) if packet.size]
        with av.open(str(fixture)) as decoded:
            samples = next(decoded.decode(audio=0)).samples
        with av.open(str(target), "w", format="webm") as output:
            copied = output.add_stream_from_template(stream)
            for index in range(round(seconds * 48000 / samples)):
                packet = av.Packet(packets[index % len(packets)])
                packet.stream = copied
                packet.time_base = Fraction(1, 48000)
                packet.pts = packet.dts = index * samples
                packet.duration = samples
                output.mux(packet)
    data = bytearray(target.read_bytes())
    offset = data.find(b"\x44\x89\x88")
    assert 0 <= offset < 4096
    data[offset : offset + 11] = b"\xec\x89" + b"\0" * 9
    target.write_bytes(data)


def encode_audio(target, seconds, codec, container, sample_format):
    rate = 8000
    with av.open(str(target), "w", format=container) as output:
        stream = output.add_stream(codec, rate=rate)
        stream.layout = "mono"
        stream.codec_context.thread_count = 1
        if codec != "flac":
            stream.bit_rate = 32000
        offset = 0
        while offset < seconds * rate:
            samples = min(4096, seconds * rate - offset)
            frame = av.AudioFrame(format=sample_format, layout="mono", samples=samples)
            frame.sample_rate = rate
            frame.time_base = Fraction(1, rate)
            frame.pts = offset
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            for packet in stream.encode(frame):
                output.mux(packet)
            offset += samples
        for packet in stream.encode(None):
            output.mux(packet)
