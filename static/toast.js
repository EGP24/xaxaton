

class ToastManager {
    constructor() {
        this.container = null;
        this.init();
    }

    init() {

        if (!document.getElementById('toast-container')) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
            this.injectStyles();
        } else {
            this.container = document.getElementById('toast-container');
        }
    }

    injectStyles() {

        if (document.getElementById('toast-styles')) return;

        const style = document.createElement('style');
        style.id = 'toast-styles';
        style.textContent = `
            .toast-container {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                display: flex;
                flex-direction: column;
                gap: 12px;
                pointer-events: none;
            }

            .toast {
                background: white;
                border-radius: 12px;
                padding: 16px 20px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12),
                            0 2px 8px rgba(0, 0, 0, 0.08);
                display: flex;
                align-items: center;
                gap: 12px;
                min-width: 300px;
                max-width: 420px;
                pointer-events: auto;
                animation: toast-slide-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
                transition: all 0.3s ease;
                border-left: 4px solid #667eea;
            }

            .toast.removing {
                animation: toast-slide-out 0.3s ease forwards;
            }

            @keyframes toast-slide-in {
                from {
                    transform: translateX(120%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }

            @keyframes toast-slide-out {
                to {
                    transform: translateX(120%);
                    opacity: 0;
                }
            }

            .toast-icon {
                font-size: 24px;
                line-height: 1;
                flex-shrink: 0;
            }

            .toast-content {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }

            .toast-title {
                font-weight: 600;
                font-size: 14px;
                color: #1f2937;
                line-height: 1.4;
            }

            .toast-message {
                font-size: 13px;
                color: #6b7280;
                line-height: 1.4;
            }

            .toast-close {
                background: none;
                border: none;
                font-size: 20px;
                color: #9ca3af;
                cursor: pointer;
                padding: 0;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 4px;
                transition: all 0.2s;
                flex-shrink: 0;
            }

            .toast-close:hover {
                background: #f3f4f6;
                color: #4b5563;
            }

            .toast.success {
                border-left-color: #10b981;
            }

            .toast.error {
                border-left-color: #ef4444;
            }

            .toast.warning {
                border-left-color: #f59e0b;
            }

            .toast.info {
                border-left-color: #3b82f6;
            }


            .toast-progress {
                position: absolute;
                bottom: 0;
                left: 0;
                height: 3px;
                background: rgba(0, 0, 0, 0.1);
                border-radius: 0 0 12px 12px;
                transform-origin: left;
                animation: toast-progress linear forwards;
            }

            @keyframes toast-progress {
                from {
                    transform: scaleX(1);
                }
                to {
                    transform: scaleX(0);
                }
            }


            @media (max-width: 640px) {
                .toast-container {
                    left: 10px;
                    right: 10px;
                    top: 10px;
                }

                .toast {
                    min-width: auto;
                    max-width: none;
                }
            }
        `;
        document.head.appendChild(style);
    }


    show({ type = 'info', title = '', message = '', duration = 4000 } = {}) {

        return null;
    }


    remove(toast) {
        toast.classList.add('removing');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }


    success(message, title = '') {
        return this.show({ type: 'success', title, message });
    }

    error(message, title = '') {
        return this.show({ type: 'error', title, message });
    }

    warning(message, title = '') {
        return this.show({ type: 'warning', title, message });
    }

    info(message, title = '') {
        return this.show({ type: 'info', title, message });
    }


    clearAll() {
        const toasts = this.container.querySelectorAll('.toast');
        toasts.forEach(toast => this.remove(toast));
    }
}


const toast = new ToastManager();


if (typeof module !== 'undefined' && module.exports) {
    module.exports = toast;
}
