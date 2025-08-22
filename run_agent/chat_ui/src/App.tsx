import { BrowserRouter, Routes, Route } from "react-router";
import Chat from "./pages/chat";
import CodeViewer from "./pages/code_viewer";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Chat />} />
        <Route path="/code" element={<CodeViewer />} />
      </Routes>
    </BrowserRouter>
  );
}
