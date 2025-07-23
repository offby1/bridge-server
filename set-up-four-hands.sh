#!/bin/bash

set -euxo pipefail

just whop
just drop migrate dcu django --detach
just stress --tiny --tempo=10
just manage four-hands
just manage cheating_bot
