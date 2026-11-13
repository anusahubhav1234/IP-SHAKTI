import { Link } from 'react-router-dom'
import { CitationItem } from '../components/Citations'

const SAMPLE = {
  number: 1, document_title: 'Sample regulations (illustration)', page_number: 12, verified: true, document_id: null,
  excerpt: 'A student must have a minimum of 75% attendance in aggregate to be eligible to appear for the semester examinations.',
}

export default function Landing() {
  return (
    <div>
      <section className="mx-auto grid max-w-6xl gap-12 px-5 py-14 lg:grid-cols-[1.05fr_1fr] lg:py-20">
        <div>
          <h1 className="font-display text-4xl font-bold leading-[1.1] sm:text-5xl">
            Ask your college documents.<br />Get the answer and the page it came from.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-muted">
            Upload regulations, notices, fee structures and placement circulars. Ask in English, Hindi or Telugu.
            Every answer quotes the passage it relies on, and the quote is checked against your document before you see it.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/register" className="btn btn-primary !px-5 !py-2.5">Create account</Link>
            <Link to="/login" className="btn btn-quiet !px-5 !py-2.5">Sign in</Link>
          </div>
        </div>

        <figure aria-label="Illustration of a cited answer">
          <div className="space-y-5 border-l-2 border-line pl-6">
            <p className="ml-auto w-fit max-w-sm rounded-panel bg-brand/10 px-4 py-2 text-[15px]">What is the minimum attendance required for examinations?</p>
            <div>
              <p className="text-[15px]">
                You need at least 75% attendance to appear for the semester examinations
                <span className="mx-0.5 rounded-sm bg-mark/70 px-1.5 text-[11px] font-semibold text-black">1</span>.
              </p>
              <ol className="mt-4"><CitationItem c={SAMPLE} open onToggle={() => {}} /></ol>
            </div>
          </div>
          <figcaption className="mt-3 text-xs text-muted">Illustration with made-up text. The marked passage is what the checker looks for in your own document.</figcaption>
        </figure>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 py-12 md:grid-cols-3">
          <div>
            <h2 className="font-display text-xl font-bold">Sources you can verify</h2>
            <p className="mt-2 text-sm text-muted">Each answer lists the document, the page and the exact quote. If a quote cannot be found in the cited passage, the answer is held back or flagged, never presented as fact.</p>
          </div>
          <div>
            <h2 className="font-display text-xl font-bold">Questions in your language</h2>
            <p className="mt-2 text-sm text-muted">Designed for English, Hindi and Telugu. Ask in one language about documents written in another. Quotes always stay in the document's own language.</p>
          </div>
          <div>
            <h2 className="font-display text-xl font-bold">Your documents stay yours</h2>
            <p className="mt-2 text-sm text-muted">Searches only cover documents in your own library. When the documents do not contain the answer, the assistant says so instead of guessing.</p>
          </div>
        </div>
      </section>
    </div>
  )
}
