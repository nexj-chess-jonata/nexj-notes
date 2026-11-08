package br.oi.cofre;

import android.app.Activity;
import android.content.DialogInterface;
import android.hardware.biometrics.BiometricManager;
import android.hardware.biometrics.BiometricPrompt;
import android.os.CancellationSignal;

public class BiometricHelper {

    public interface Listener {
        void onResult(boolean ok, String msg);
    }

    public static boolean available(Activity a) {
        try {
            BiometricManager m = a.getSystemService(BiometricManager.class);
            return m != null && m.canAuthenticate() == BiometricManager.BIOMETRIC_SUCCESS;
        } catch (Throwable t) {
            return false;
        }
    }

    public static void authenticate(final Activity a, final String title, final Listener l) {
        a.runOnUiThread(new Runnable() {
            public void run() {
                try {
                    BiometricPrompt prompt = new BiometricPrompt.Builder(a)
                        .setTitle(title)
                        .setNegativeButton("Usar senha", a.getMainExecutor(),
                            new DialogInterface.OnClickListener() {
                                public void onClick(DialogInterface d, int w) {
                                    l.onResult(false, "");
                                }
                            })
                        .build();
                    prompt.authenticate(new CancellationSignal(), a.getMainExecutor(),
                        new BiometricPrompt.AuthenticationCallback() {
                            public void onAuthenticationSucceeded(
                                    BiometricPrompt.AuthenticationResult r) {
                                l.onResult(true, "");
                            }
                            public void onAuthenticationError(int code, CharSequence msg) {
                                l.onResult(false, msg == null ? "" : msg.toString());
                            }
                        });
                } catch (Throwable t) {
                    l.onResult(false, String.valueOf(t.getMessage()));
                }
            }
        });
    }
}
