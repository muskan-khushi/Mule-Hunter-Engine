import LoginForm from "../components/LoginForm";
import Navbar from "../components/Navbar";
import Testimonials from "../components/Testimonial";

export default function Home() {
  return (
    <main className="h-screen  bg-[#141414] text-white font-sans selection:bg-[#CAFF33] selection:text-black">
      <Navbar/>
      <div className="container mx-auto px-4 my-26">
        <LoginForm/>
      </div>
      <footer className="bg-[#1A1A1A] py-6 border-t border-gray-800 text-center text-gray-500 text-sm">
        © 2025 MULE HUNTER. All Rights Reserved.
      </footer>
    </main>
  );
}