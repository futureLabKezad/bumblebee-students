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

using System.Collections.Concurrent;
using BumblebeeGcs.Logic;

namespace BumblebeeGcs.Logic.Tests.Fakes;

/// <summary>
/// The UI thread for socket tests: one worker thread runs the queued actions in order,
/// as the WinUI DispatcherQueue does. Tests read the store through Run, on that thread.
/// </summary>
public sealed class TestUiQueue : IUiQueue, IDisposable
{
    private readonly BlockingCollection<Action> _queue = new();
    private readonly Thread _thread;
    private Exception? _failure;

    public TestUiQueue()
    {
        _thread = new Thread(Loop) { IsBackground = true, Name = "test-ui" };
        _thread.Start();
    }

    public bool HasThreadAccess => Thread.CurrentThread == _thread;

    public bool TryEnqueue(Action action)
    {
        try
        {
            _queue.Add(action);
            return true;
        }
        catch (InvalidOperationException)
        {
            return false;   // disposed
        }
    }

    /// <summary>Run on the UI thread and wait for the result; rethrows a failure of any earlier action.</summary>
    public T Run<T>(Func<T> f)
    {
        if (_failure is Exception earlier) throw new InvalidOperationException("an action on the UI thread failed", earlier);
        if (HasThreadAccess) return f();
        var done = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!TryEnqueue(() =>
            {
                try { done.SetResult(f()); }
                catch (Exception e) { done.SetException(e); }
            }))
            throw new ObjectDisposedException(nameof(TestUiQueue));
        if (!done.Task.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException("UI thread did not answer");
        return done.Task.Result;
    }

    public void Run(Action a) => Run(() => { a(); return 0; });

    private void Loop()
    {
        foreach (var a in _queue.GetConsumingEnumerable())
        {
            try { a(); }
            catch (Exception e) { _failure ??= e; }
        }
    }

    public void Dispose() => _queue.CompleteAdding();
}
