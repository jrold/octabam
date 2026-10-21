#!/usr/bin/env python3
"""Attribute the production CF calibration deadline with read-only profiling.

No Part change occurs in this capture: the original once-seeded witness is
valid here because the first event resets to the same pristine initial state.
Actual Part/generation exactness belongs to the production observer campaign.
"""
import sys
import qualify_perky_noise_hat_production as p
import profile_perky_noise_hat_handoff as profile
if __name__=='__main__':
 profile.q.c.stage_fixture=p.stage
 sys.argv=[sys.argv[0],'--work',str(p.SOURCE/'cf-profile'),'--source',str(p.SOURCE),'--case','cf-calibration']
 profile.main()
