import Link from "next/link";

export default function NotFound() {
  return (
    <div className="max-w-lg mx-auto text-center py-16 animate-fade-in">
      <h2 className="text-xl font-bold mb-2">Page not found</h2>
      <p className="text-sm text-gray-400 mb-6">
        That page does not exist.
      </p>
      <Link
        href="/"
        className="btn-animated inline-block px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-xl text-sm font-medium border border-gray-700"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
