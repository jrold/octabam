// Capture the installed PerkyBits AU through Apple's AudioUnit API, no device/FX.
#include <AudioToolbox/AudioToolbox.h>
#include <CoreFoundation/CoreFoundation.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
#include <cstring>
#include <cmath>
struct Event { unsigned sample,status,data1,data2; };
static void ck(OSStatus s,const char*w){if(s){fprintf(stderr,"%s: %d\n",w,int(s));exit(1);}}
static std::string cs(CFStringRef s){char b[2048]={};if(s)CFStringGetCString(s,b,sizeof b,kCFStringEncodingUTF8);return b;}
int main(int argc,char**argv){
 double rate=48000,seconds=4;unsigned block=256,note=45,velocity=127,prime=0;std::string firmware,out,midi;
 std::vector<std::pair<unsigned,float>> params;
 for(int i=1;i<argc;++i){std::string a=argv[i];auto next=[&](){if(i+1>=argc){fprintf(stderr,"missing value for %s\n",a.c_str());exit(2);}return std::string(argv[++i]);};if(a=="--midi")midi=next();else if(a=="--firmware")firmware=next();else if(a=="--out")out=next();else if(a=="--rate")rate=std::stod(next());else if(a=="--seconds")seconds=std::stod(next());else if(a=="--prime")prime=std::stoul(next());else if(a=="--block")block=std::stoul(next());else if(a=="--note")note=std::stoul(next());else if(a=="--velocity")velocity=std::stoul(next());else if(a=="--set"){unsigned id=std::stoul(next());float v=std::stof(next());params.emplace_back(id,v);}else return 2;}
 if(rate<8000 || rate>192000 || seconds<=0 || seconds>60 || block==0 || block>32768 || note>127 || velocity==0 || velocity>127)return 2;
 AudioComponentDescription d={'aumu','PkBt','Prky',0,0};auto c=AudioComponentFindNext(nullptr,&d);if(!c)return 3;UInt32 version=0;ck(AudioComponentGetVersion(c,&version),"version");printf("version=%u\n",version);if(version!=512){fprintf(stderr,"capture host qualifies PerkyBits 0.2.0 (component 512) only\n");return 3;}
 AudioUnit u=nullptr;ck(AudioComponentInstanceNew(c,&u),"instantiate");
 AudioStreamBasicDescription f={};f.mSampleRate=rate;f.mFormatID=kAudioFormatLinearPCM;f.mFormatFlags=kAudioFormatFlagsNativeFloatPacked|kAudioFormatFlagIsNonInterleaved;f.mBytesPerFrame=f.mBytesPerPacket=4;f.mFramesPerPacket=1;f.mChannelsPerFrame=2;f.mBitsPerChannel=32;
 ck(AudioUnitSetProperty(u,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Output,0,&f,sizeof f),"format");ck(AudioUnitSetProperty(u,kAudioUnitProperty_MaximumFramesPerSlice,kAudioUnitScope_Global,0,&block,sizeof block),"block");ck(AudioUnitInitialize(u),"init");
 UInt32 size=0;Boolean wr=false;ck(AudioUnitGetPropertyInfo(u,kAudioUnitProperty_ParameterList,kAudioUnitScope_Global,0,&size,&wr),"list size");std::vector<unsigned> ids(size/4);ck(AudioUnitGetProperty(u,kAudioUnitProperty_ParameterList,kAudioUnitScope_Global,0,ids.data(),&size),"list");
 for(auto id:ids){AudioUnitParameterInfo inf={};size=sizeof inf;ck(AudioUnitGetProperty(u,kAudioUnitProperty_ParameterInfo,kAudioUnitScope_Global,id,&inf,&size),"info");float val;ck(AudioUnitGetParameter(u,id,kAudioUnitScope_Global,0,&val),"value");printf("%u\t%s\t%.9g\t%.9g\t%.9g\n",id,(inf.flags&kAudioUnitParameterFlag_HasCFNameString?cs(inf.cfNameString):std::string(inf.name)).c_str(),inf.minValue,inf.maxValue,val);}
 if(!firmware.empty()){
 CFPropertyListRef state=nullptr;size=sizeof state;ck(AudioUnitGetProperty(u,kAudioUnitProperty_ClassInfo,kAudioUnitScope_Global,0,&state,&size),"get state");auto dict=CFDictionaryCreateMutableCopy(nullptr,0,(CFDictionaryRef)state);
 // JUCE copyXmlToBinary: little-endian magic, byte length, UTF-8 XML, NUL.
 std::string xml="<PARAMETERS firmwarePath=\""+firmware+"\" engineSwitchDeclick=\"0\">";
 const std::pair<unsigned,const char*> names[]={{3571704,"tune"},{95459258,"decay"},{1152055620,"param1"},{1152055621,"param2"},{3357091,"mode"},{848820802,"engine"},{1544507992,"chromatic"},{2134260957,"velocity"}};
 for(auto pair:names){float val;ck(AudioUnitGetParameter(u,pair.first,kAudioUnitScope_Global,0,&val),"state parameter");for(auto p:params)if(p.first==pair.first)val=p.second;float scale=pair.first==848820802?1:pair.first==3357091?2:pair.first==1544507992?1:pair.first==2134260957?255:4095;xml+="<PARAM id=\""+std::string(pair.second)+"\" value=\""+std::to_string(std::lround(val*scale))+"\"/>";}
 xml+="</PARAMETERS>";std::vector<unsigned char> blob(9+xml.size());unsigned magic=0x21324356,len=xml.size();memcpy(blob.data(),&magic,4);memcpy(blob.data()+4,&len,4);memcpy(blob.data()+8,xml.data(),len);
 auto data=CFDataCreate(nullptr,blob.data(),blob.size());CFDictionarySetValue(dict,CFSTR("jucePluginState"),data);CFPropertyListRef value=dict;ck(AudioUnitSetProperty(u,kAudioUnitProperty_ClassInfo,kAudioUnitScope_Global,0,&value,sizeof value),"restore firmware");CFRelease(data);CFRelease(dict);CFRelease(state);
 }
 for(auto p:params)ck(AudioUnitSetParameter(u,p.first,kAudioUnitScope_Global,0,p.second,0),"set");
 if(!out.empty()){
 std::ofstream dest(out,std::ios::binary);if(!dest)return 4;std::vector<float> l(block),r(block);struct B{unsigned n;AudioBuffer b[2];}buf={2,{{1,block*4,l.data()},{1,block*4,r.data()}}};
 std::vector<Event> events;
 if(!midi.empty()){std::ifstream file(midi);Event event;if(!file)return 4;while(file>>event.sample>>event.status>>event.data1>>event.data2)events.push_back(event);if(!file.eof() || !std::is_sorted(events.begin(),events.end(),[](auto x,auto y){return x.sample<y.sample;}))return 4;}
 size_t next=0;
 // Optional idle priming is explicit. The default is a fresh sample-zero trigger.
 for(unsigned at=0;at<prime*block+unsigned(rate*seconds);at+=block){unsigned n=std::min(block,prime*block+unsigned(rate*seconds)-at);if(at==prime*block)ck(MusicDeviceMIDIEvent(u,0x90,note,velocity,0),"note on");if(at>=prime*block)while(next<events.size() && events[next].sample<at-prime*block+n){auto ev=events[next++];ck(MusicDeviceMIDIEvent(u,ev.status,ev.data1,ev.data2,ev.sample-(at-prime*block)),"scheduled MIDI");}AudioTimeStamp t={};t.mSampleTime=at;t.mFlags=kAudioTimeStampSampleTimeValid;AudioUnitRenderActionFlags flags=0;buf.b[0].mDataByteSize=buf.b[1].mDataByteSize=n*4;ck(AudioUnitRender(u,&flags,&t,0,n,(AudioBufferList*)&buf),"render");if(at>=prime*block)for(unsigned j=0;j<n;++j){dest.write((char*)&l[j],4);dest.write((char*)&r[j],4);}}
 }
 ck(AudioUnitUninitialize(u),"uninit");ck(AudioComponentInstanceDispose(u),"dispose");
}
