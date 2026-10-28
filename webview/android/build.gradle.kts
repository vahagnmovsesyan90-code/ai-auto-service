plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
    // Push ծանուցումներ (FCM). կիրառվում է միայն app/google-services.json-ի առկայությամբ (տես app/build.gradle.kts)
    id("com.google.gms.google-services") version "4.4.2" apply false
}
