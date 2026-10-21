#pragma once
#include <array>
#include <map>
#include <fstream>
#include <cstdlib>
#include <cstdint>
// Read-only common-path census for the stock sample-position recurrence.
// Ordinary RAM peeks only; no target instructions or state are changed.
namespace stock_position_cost {
struct Observer {
 const char*path=std::getenv("CF_STOCK_POSITION_REPORT");
 uint64_t entries=0,unity=0,inner_steps=0,cycles=0,last_cycle=0;
 bool last_in_region=false;
 std::map<std::array<uint64_t,3>,uint64_t>pairs;
 std::map<uint32_t,uint64_t>objects;
 template<class M>void step(M&m,unsigned pc){
  if(!path)return;
  bool active=hybrid_safety::observer.returns>=512;
  bool here=active&&pc>=0x4000888e&&pc<0x400088b0;
  if(last_in_region||here){auto now=m.getCycles();if(last_in_region)cycles+=now-last_cycle;last_cycle=now;}
  last_in_region=here;
  if(!active)return;
  if(pc==0x40008890)inner_steps++;
  if(pc!=0x4000888e)return;
  auto object=m.getA(2),count=m.getD(4);
  uint64_t fraction=(uint64_t(m.getD(0))<<32)|m.getD(1);
  uint64_t decrement=(uint64_t(m.peek32(object+128))<<32)|m.peek32(object+132);
  uint64_t period=(uint64_t(m.peek32(object+136))<<32)|m.peek32(object+140);
  entries++;objects[object]++;pairs[{decrement,period,count}]++;
  if(decrement==period&&period&&!(period>>63)&&!(fraction>>63)&&fraction<period&&count<=0x7fffffffu)unity++;
 }
 ~Observer(){if(!path)return;std::ofstream f(path);f<<"{\"entries\":"<<entries<<",\"unity_guard_hits\":"<<unity
  <<",\"inner_sample_steps\":"<<inner_steps<<",\"region_cycles\":"<<cycles<<",\"pairs\":[";
  bool comma=false;for(auto&v:pairs){f<<(comma?",":"")<<"{\"step\":"<<v.first[0]<<",\"period\":"<<v.first[1]
   <<",\"count\":"<<v.first[2]<<",\"calls\":"<<v.second<<'}';comma=true;}
  f<<"],\"objects\":[";comma=false;for(auto&v:objects){f<<(comma?",":"")<<"{\"address\":"<<v.first<<",\"calls\":"<<v.second<<'}';comma=true;}
  f<<"]}\n";
 }
};inline Observer observer;
}
