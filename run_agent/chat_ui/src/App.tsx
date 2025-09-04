import { BrowserRouter, Routes, Route } from "react-router";
import Chat from "./pages/chat";
import CodeViewer from "./pages/code_viewer";
import { Helmet } from "react-helmet";

export default function App() {
  return (
    <>
      <Helmet>
        {/* <script src="https://unpkg.com/vue@next" defer /> */}
      </Helmet>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/code" element={<CodeViewer />} />
        </Routes>
      </BrowserRouter>
    </>
  );
}
