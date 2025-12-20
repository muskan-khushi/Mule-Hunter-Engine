"use client";
import { useState } from 'react';

const LoginForm = () => {
  const [role, setRole] = useState('Admin');
  const roles = ['Admin', 'Investigator', 'Viewer'];

  return (
    <div className="max-w-2xl mx-auto mt-16 p-10 bg-[#1C1C1C] rounded-2xl border border-gray-800 shadow-2xl text-center">
      <h1 className="text-[#CAFF33] text-4xl font-semibold mb-2">Login</h1>
      <p className="text-gray-400 mb-10">Welcome back! Please select your access level and log in.</p>
      
      <form className="space-y-6">
        {/* Role Selector Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-medium uppercase tracking-widest text-gray-500">Access Level</span>
            <span className="text-xs text-[#CAFF33] font-mono">{role} Mode</span>
          </div>
          
          <div className="flex p-1.5 bg-[#141414] rounded-xl border border-gray-800 gap-1">
            {roles.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRole(r)}
                className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
                  role === r 
                  ? "bg-[#262626] text-[#CAFF33] shadow-lg border border-gray-700" 
                  : "text-gray-500 hover:text-gray-300 hover:bg-[#1a1a1a]"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        {/* Input Fields */}
        <div className="space-y-4">
          <input 
            type="email" 
            placeholder="Enter your Email" 
            className="w-full bg-[#141414] border border-gray-800 p-4 rounded-lg text-white focus:outline-none focus:border-[#CAFF33] transition-all"
            required
          />
          <input 
            type="password" 
            placeholder="Enter your Password" 
            className="w-full bg-[#141414] border border-gray-800 p-4 rounded-lg text-white focus:outline-none focus:border-[#CAFF33] transition-all"
            required
          />
        </div>
        
        <div className="text-right">
          <a href="#" className="text-sm text-gray-400 hover:text-[#CAFF33] underline underline-offset-4">Forgot Password?</a>
        </div>
        
        {/* Action Buttons */}
        <div className="space-y-3 pt-4">
          <button className="w-full bg-[#CAFF33] py-4 rounded-lg font-bold text-black hover:bg-[#b8e62e] transition-all">
            Login as {role}
          </button>
          <button type="button" className="w-full bg-transparent py-4 rounded-lg font-bold text-white border border-gray-800 hover:bg-[#262626] transition-all">
            Request Access
          </button>
        </div>
      </form>
    </div>
  );
};

export default LoginForm;