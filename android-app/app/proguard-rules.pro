# Modelos serializados con Gson: conservar nombres de campos.
-keep class mx.freshtrack.mobile.data.model.** { *; }
-keepattributes Signature, *Annotation*, InnerClasses, EnclosingMethod
# Retrofit
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class retrofit2.Response
-keep,allowobfuscation,allowshrinking class kotlin.coroutines.Continuation
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# R8 full mode (AGP 9): conservar constructores que se invocan por reflexión.
# WorkManager crea su base Room y los Workers por reflexión.
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep class * extends androidx.work.ListenableWorker { <init>(android.content.Context, androidx.work.WorkerParameters); }
-keep class * implements androidx.startup.Initializer { <init>(); }
# ML Kit descubre sus componentes por reflexión.
-keep class * implements com.google.firebase.components.ComponentRegistrar { <init>(); }

# Cola de trabajo sin conexión (se guarda como JSON con Gson).
-keep class mx.freshtrack.mobile.data.offline.** { *; }
