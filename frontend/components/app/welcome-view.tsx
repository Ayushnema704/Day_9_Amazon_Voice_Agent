import { Button } from '@/components/livekit/button';
import Image from 'next/image';

function WelcomeImage() {
  return (
    <div className="relative mb-8 flex justify-center">
      <div className="relative z-10">
        <Image 
          src="/assets/logo.png" 
          alt="Amazon Logo" 
          width={280} 
          height={280}
          style={{ width: 'auto', height: 'auto' }}
          priority
        />
      </div>
    </div>
  );
}

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: () => void;
}

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  return (
    <div ref={ref} className="min-h-screen flex items-center justify-center bg-[rgba(22,29,40,1)]">
      <section className="flex flex-col items-center justify-center text-center px-4 py-12 max-w-3xl">
        <WelcomeImage />

        <h1 className="text-foreground text-4xl md:text-6xl font-bold mb-4 bg-gradient-to-r from-orange-500 via-orange-400 to-yellow-400 dark:from-orange-400 dark:to-yellow-300 bg-clip-text text-transparent drop-shadow-lg">
          Amazon Voice Shopping
        </h1>

        <p className="text-foreground/90 text-lg md:text-xl max-w-2xl pt-2 leading-7 font-medium">
          Shop smarter with voice - Your AI shopping assistant for electronics, books, fashion & more
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8 mb-8 w-full max-w-2xl">
          <div className="bg-card/50 backdrop-blur p-5 rounded-xl border border-orange-900/50 hover:border-orange-600/50 transition-colors">
            <div className="text-3xl mb-2">🎧</div>
            <h3 className="font-semibold text-foreground mb-1">Voice Search</h3>
            <p className="text-sm text-muted-foreground">Find products instantly by speaking</p>
          </div>
          <div className="bg-card/50 backdrop-blur p-5 rounded-xl border border-orange-900/50 hover:border-orange-600/50 transition-colors">
            <div className="text-3xl mb-2">🛍</div>
            <h3 className="font-semibold text-foreground mb-1">Smart Cart</h3>
            <p className="text-sm text-muted-foreground">Manage your cart hands-free</p>
          </div>
          <div className="bg-card/50 backdrop-blur p-5 rounded-xl border border-orange-900/50 hover:border-orange-600/50 transition-colors">
            <div className="text-3xl mb-2">⚡</div>
            <h3 className="font-semibold text-foreground mb-1">Fast Checkout</h3>
            <p className="text-sm text-muted-foreground">Complete orders in seconds</p>
          </div>
        </div>

        <Button
          variant="primary"
          size="lg"
          onClick={onStartCall}
          className="mt-4 px-8 py-6 text-lg font-semibold transition-all bg-gradient-to-r from-orange-600 to-orange-500 hover:from-orange-500 hover:to-orange-400"
        >
          {startButtonText}
        </Button>

        <p className="text-muted-foreground text-sm mt-6">
          Click to start voice shopping with your AI assistant
        </p>
      </section>
    </div>
  );
};
