import { Component, input, output, signal } from '@angular/core';

@Component({
  selector: 'app-composer',
  templateUrl: './composer.html',
  styleUrl: './composer.css',
})
export class ComposerComponent {
  readonly disabled = input(false);
  readonly send = output<string>();

  protected readonly draft = signal('');

  protected submit(): void {
    const text = this.draft().trim();
    if (!text || this.disabled()) {
      return;
    }
    this.send.emit(text);
    this.draft.set('');
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.submit();
    }
  }
}
