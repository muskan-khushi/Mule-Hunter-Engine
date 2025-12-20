import Image from 'next/image';
import React from 'react';

const Navbar = () => {
  return (
    <nav className="flex items-center justify-between px-8 py-6 bg-[#1A1A1A] border-b border-gray-800">
      <div className="flex items-center gap-2">
        <div className="flex items-center justify-center">
           <Image src="/logo.png" alt="Logo" width={160} height={200}/>
        </div>
      </div>
      <div className="hidden md:flex gap-6 text-gray-300">
        <a href="#" className="hover:text-[#CAFF33]">Home</a>
        <a href="#" className="hover:text-[#CAFF33]">Network</a>
        <a href="#" className="hover:text-[#CAFF33]">Alerts</a>
        <a href="#" className="hover:text-[#CAFF33]">Stats</a>
      </div>
      <div className="flex gap-4 items-center">
        <button className="text-white">Sign Up</button>
        <button className="bg-[#CAFF33] px-6 py-2 rounded-full text-black font-medium">Login</button>
      </div>
    </nav>
  );
};

export default Navbar;