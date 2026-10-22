// Copyright 2026 FutureLab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

using BumblebeeGcs.Logic;
using Microsoft.UI.Dispatching;

namespace BumblebeeGcs.Services;

/// <summary>The WinUI UI thread as an IUiQueue (RosbridgeClient has no WinUI dependency).</summary>
public sealed class DispatcherUiQueue : IUiQueue
{
    private readonly DispatcherQueue _dq;

    public DispatcherUiQueue(DispatcherQueue dq) => _dq = dq;

    public bool HasThreadAccess => _dq.HasThreadAccess;

    public bool TryEnqueue(Action action) => _dq.TryEnqueue(() => action());
}
