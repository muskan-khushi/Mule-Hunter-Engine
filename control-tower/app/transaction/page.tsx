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

    const transactionData = {
      sourceAccount: form.source,
      targetAccount: form.target,
      amount: Number(form.amount)
    };

    try {
      const txResponse = await fetch("http://localhost:8080/api/transactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(transactionData),
      });

      if (!txResponse.ok) throw new Error("Transaction Failed");

      const data = await txResponse.json();
      console.log("Full Backend Response:", data); 

      setResult({
        risk_score: data.riskScore || 0,
        
        reasons: [data.verdict || "Processed by AI Engine"]
      });

    } catch (error) {
      console.error("Error:", error);
      alert("Transaction Failed! Check console for details.");
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

            <div className="flex-1 overflow-y-auto pr-2 space-y-4">

              {/* {!result && (
                <div className="h-full flex items-center justify-center border-2 border-dashed border-gray-800 rounded-xl">
                  <p className="text-gray-500 italic">
                    Submit a transaction to trigger AI analysis
                  </p>
                </div>
              )} */}

              {result && (
                <>
                  {/* 🧬 CARD 1 — Unsupervised ML*/}
                  <div className="p-4 bg-gray-900 rounded-xl border border-gray-800">
                    <h3 className="font-semibold mb-2 text-[#caff33]">
                      🧬 Feature Engineering
                    </h3>

                    <p className="text-sm text-gray-400 mb-2">
                      Graph-based features constructed for this account
                    </p>

                    <div className="text-xs text-gray-300 space-y-1">
                      <div>Out-degree: {result.features.before.out_degree} → {result.features.after.out_degree}</div>
                      <div>Risk Ratio: {result.features.before.risk_ratio} → {result.features.after.risk_ratio}</div>
                      <div>Compared against {result.features.populationSize} accounts</div>
                    </div>
                  </div>

                  {/* 🟠 CARD 2 — JA3 Device fingerprinting */}

                  <div className="p-4 bg-gray-900 rounded-xl border border-gray-800">
                    <h3 className="font-semibold mb-2 text-red-400">
                      🔗 Device & Pattern Correlation
                    </h3>

                    {!result.correlation.ja3Detected ? (
                      <p className="text-sm text-gray-400">
                        No shared device fingerprint or coordinated activity detected.
                      </p>
                    ) : (
                      <>
                        <p className="text-sm text-gray-300">
                          Shared device fingerprint detected across accounts:
                        </p>
                        <ul className="list-disc list-inside text-sm text-red-300 mt-2">
                          {result.correlation.linkedAccounts.map((a: string, i: number) => (
                            <li key={i}>{a}</li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                   {/* 🔗Supervised Model */}
                  <div className="p-4 bg-gray-900 rounded-xl border border-gray-800">
                    <h3 className="font-semibold mb-2 text-orange-400">
                      🟠 Behavioral Anomaly Detection
                    </h3>

                    <p className="text-sm text-gray-400">
                      Model: {result.unsupervised.model}
                    </p>

                    <div className="mt-2 text-sm">
                      Anomaly Score:{" "}
                      <span className="font-bold">
                        {result.unsupervised.score}
                      </span>
                    </div>

                    <div className={`mt-1 text-sm font-semibold ${
                      result.unsupervised.isAnomalous
                        ? "text-red-500"
                        : "text-green-400"
                    }`}>
                      {result.unsupervised.isAnomalous
                        ? "Anomalous Behavior Detected"
                        : "Behavior Within Normal Range"}
                    </div>
                  </div>

                 
                  

                  {/* 🚨 CARD 4 — Final Decision */}
                  <div className="p-4 bg-gray-900 rounded-xl border border-gray-800">
                    <h3 className="font-semibold mb-2 text-red-500">
                      🚨 Final Risk Assessment
                    </h3>

                    <div className="text-sm text-gray-300">
                      Risk Level:{" "}
                      <span className="font-bold">{result.final.riskLevel}</span>
                    </div>

                    <div className="text-sm text-gray-400 mt-1">
                      Confidence: {result.final.confidence}
                    </div>

                    <div className="mt-3 flex gap-3">
                      <button className="px-3 py-1 rounded-md bg-[#caff33] text-black text-sm font-semibold">
                        Generate Report
                      </button>

                      <button className="px-3 py-1 rounded-md border border-gray-700 text-sm">
                        View in Graph
                      </button>
                    </div>
                  </div>
                </>
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