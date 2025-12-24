"use client";

import { useState } from "react";
import Footer from "../components/Footer";

export default function FakeTransactionPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const [form, setForm] = useState({
    source: "",
    target: "",
    amount: "",
  });

  const handleChange = (e: any) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const sendTransaction = async () => {
    setLoading(true);
    setResult(null);

    const payload = {
      source: form.source,
      target: form.target,
      amount: Number(form.amount),
      timestamp: Date.now(),
    };

    try {
      // 1️⃣ Send transaction (graph edge)
      await fetch("http://localhost:8080/api/transaction", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const res = await fetch(`/backend/api/risk-scores/${form.source}`);
      const data = await res.json();

      setResult(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    // Wrapper: h-screen makes it exactly the height of the viewport
    // flex-col allows the Footer to sit at the bottom
    <div className="flex flex-col h-screen bg-black text-white">
      
      {/* MAIN CONTENT AREA: flex-1 takes up all available space above the footer */}
      <main className="flex-1 overflow-hidden p-6 lg:p-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-full">

          {/* LEFT PANEL */}
          <div className="border border-gray-800 rounded-2xl p-6 flex flex-col h-full bg-[#0A0A0A]">
            <h2 className="text-xl font-bold mb-6 shrink-0">
              Fake Transaction (Graph Edge)
            </h2>

            <div className="flex flex-col gap-4 overflow-y-auto pr-2">
              <input
                name="source"
                placeholder="Source Account ID"
                className="bg-gray-900 p-3 rounded-lg border border-gray-700 focus:border-[#caff33] outline-none transition"
                onChange={handleChange}
              />

              <input
                name="target"
                placeholder="Target Account ID"
                className="bg-gray-900 p-3 rounded-lg border border-gray-700 focus:border-[#caff33] outline-none transition"
                onChange={handleChange}
              />

              <input
                name="amount"
                type="number"
                placeholder="Amount (₹)"
                className="bg-gray-900 p-3 rounded-lg border border-gray-700 focus:border-[#caff33] outline-none transition"
                onChange={handleChange}
              />

              <div className="text-xs text-gray-500">
                Timestamp will be auto-generated
              </div>

              <button
                onClick={sendTransaction}
                disabled={loading}
                className="mt-4 bg-[#caff33] hover:bg-[#b8e62e] text-black cursor-pointer transition p-3 rounded-xl font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? "Analyzing..." : "Send Transaction"}
              </button>
            </div>
          </div>

          {/* RIGHT PANEL */}
          <div className="border border-gray-800 rounded-2xl p-6 flex flex-col h-full bg-[#0A0A0A]">
            <h2 className="text-xl font-bold mb-6 shrink-0">
              AI Decision Panel
            </h2>

            <div className="flex-1 overflow-y-auto pr-2">
              {!result && (
                <div className="h-full flex items-center justify-center border-2 border-dashed border-gray-800 rounded-xl">
                    <p className="text-gray-500 italic">
                        Submit a transaction to trigger AI analysis
                    </p>
                </div>
              )}

              {result && (
                <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-2">
                  <div className="p-4 bg-gray-900 rounded-xl border border-gray-800">
                    <div className="text-sm text-gray-400">Risk Score</div>
                    <div className={`text-3xl font-bold ${result.risk_score > 70 ? 'text-red-500' : 'text-yellow-500'}`}>
                      {result.risk_score}
                    </div>
                  </div>

                  <div className="p-4 bg-gray-900 rounded-xl border border-gray-800">
                    <div className="text-sm text-gray-400 mb-2">
                      Why flagged?
                    </div>
                    <ul className="list-disc list-inside text-sm text-gray-300 space-y-2">
                      {result.reasons?.map((r: string, i: number) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          </div>

        </div>
      </main>

      {/* FOOTER: Fixed to the bottom */}
      <footer className="shrink-0">
        <Footer />
      </footer>
    </div>
  );
}