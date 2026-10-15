// Reuse the pinned real-task initialization and interrupted storage assertions,
// then census both controllers on the changed actual image after card mount.
#define main checkpoint_stack_probe
#include "stack_ownership.cpp"
#undef main
int main(int argc,char** argv) {
    const auto result=checkpoint_stack_probe(argc,argv);assert(result==0);
    ot::Machine m(load(argv[1]));assert(m.run(50'000'000)==ot::Machine::Stop::Handoff);
    ot::AtaCard card(load(argv[2]));ot::Rtos r(m,3990,132e6,false);
    r.attachCard(card);r.mapCardMemory();r.install();
    assert(r.runToMainSpin()==ot::Rtos::Stop::Gate);
    assert(r.requestCardMount());
    assert(r.runUntil(10000,[&]{return m.peek32(ot::g_cardReady)!=0;})==ot::Rtos::Stop::Gate);
    assert(r.runToMainSpin()==ot::Rtos::Stop::Gate);
    for(unsigned controller=0;controller<2;++controller) {
        const auto base=controller?ot::g_intc1:ot::g_intc0;
        for(unsigned source=1;source<64;++source) {
            auto v=64+controller*64+source;auto icr=m.read8(base+0x40+source);
            auto handler=m.peek32(m.vbr()+4*v);
            if(handler!=0x40000d74)
                std::printf("IRQ_CONFIG vector=%02x ICR=%02x handler=%08x\n",v,icr,handler);
        }
    }
    return 0;
}
