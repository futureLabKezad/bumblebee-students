"""Independent PARAM_SET wire audit; forwarded only after successful sendto."""
import struct
import time

def param_set_record(msg,forwarded):
    name=msg.param_id
    if isinstance(name,bytes): name=name.split(b'\0',1)[0].decode('ascii',errors='backslashreplace')
    else: name=str(name).split('\0',1)[0]
    return dict(name=name,param_type=msg.param_type,value=msg.param_value,
        wire_float_bits=struct.pack('<f',msg.param_value).hex(),
        source_system=msg.get_srcSystem(),source_component=msg.get_srcComponent(),
        target_system=msg.target_system,target_component=msg.target_component,
        forwarded=bool(forwarded))

def forward_outbound(frame,msg,send,record,observation=None,clock=time.monotonic):
    is_set=msg.get_type()=='PARAM_SET'
    try:
        sent=send(frame)
        if sent!=len(frame): raise OSError('incomplete datagram send')
    except OSError:
        if is_set: record('param_set', **param_set_record(msg,False))
        raise
    if is_set: record('param_set', **param_set_record(msg,True))
    if observation is not None:
        kind=msg.get_type()
        source=(msg.get_srcSystem(),msg.get_srcComponent())
        if source!=(255,190) or kind not in ('RC_CHANNELS_OVERRIDE','HEARTBEAT'): return
        now=clock()
        if now-observation.get(kind,float('-inf'))<1.: return
        observation[kind]=now
        fields=dict(source_system=source[0],source_component=source[1],forwarded=True)
        if kind=='RC_CHANNELS_OVERRIDE':
            fields.update(target_system=msg.target_system,target_component=msg.target_component,
                          channels=[getattr(msg,'chan'+str(i)+'_raw') for i in range(1,19)])
            record('rc_forwarded',**fields)
        else:
            fields.update(base_mode=msg.base_mode,autopilot=msg.autopilot)
            record('gcs_heartbeat_forwarded',**fields)
